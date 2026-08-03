#!/usr/bin/env python3
"""Prüft Avatar-Sätze und baut versionierte, sichere .tar.gz-Bundles für Pages."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path

REQUIRED = {
    "base.png", "portrait.png", "profile_640.png", "profile_640_kreis-vorschau.png",
    "eyes_half.png", "eyes_closed.png", "eyes_wink_left.png", "manifest.json",
    *(f"mouth_{name}.png" for name in "XABCDEFGH"),
    *(f"brows_{name}.png" for name in ("neutral", "happy", "sad", "surprised", "angry", "thinking", "playful")),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(avatar: Path) -> tuple[str, int]:
    manifest_path = avatar / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{avatar}: manifest.json ist ungültig: {exc}") from exc
    name = manifest.get("name")
    version = manifest.get("version")
    if name != avatar.name or not isinstance(version, int) or version < 1:
        raise ValueError(f"{avatar}: manifest.name muss '{avatar.name}' und version eine positive Ganzzahl sein")
    missing = sorted(name for name in REQUIRED if not (avatar / name).is_file())
    if missing:
        raise ValueError(f"{avatar}: fehlende Pflichtdateien: {', '.join(missing)}")
    # Der Renderer darf nie auf einen nicht vorhandenen Layer zeigen.
    references = [manifest.get("base"), manifest.get("portrait")]
    references.extend(item.get("file") for item in manifest.get("visemes", {}).get("layers", {}).values())
    references.extend(item.get("file") for item in manifest.get("eyes", {}).values())
    references.extend(item.get("file") for item in manifest.get("brows", {}).values())
    dangling = sorted({ref for ref in references if ref and not (avatar / ref).is_file()})
    if dangling:
        raise ValueError(f"{avatar}: Manifest referenziert fehlende Dateien: {', '.join(dangling)}")
    return name, version


def bundle(avatar: Path, output: Path) -> None:
    """Baut ein bitgleiches Archiv: feste Reihenfolge, Zeitstempel, Eigentümer und Rechte.

    Ohne das ändert schon der gzip-Zeitstempel bei jedem Lauf die Prüfsumme, und eine
    veröffentlichte SHA-256 wäre nicht nachprüfbar.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(avatar.rglob("*")):
            if not path.is_file():
                continue
            info = archive.gettarinfo(str(path), arcname=str(path.relative_to(avatar)))
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    with output.open("wb") as target:
        with gzip.GzipFile(fileobj=target, mode="wb", mtime=0, compresslevel=9):
            pass
    with output.open("wb") as target:
        gz = gzip.GzipFile(filename="", fileobj=target, mode="wb", mtime=0, compresslevel=9)
        gz.write(raw.getvalue())
        gz.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument("--avatar", action="append", help="Nur diesen Satz bauen (wiederholbar)")
    args = parser.parse_args()
    root = Path.cwd()
    selected = set(args.avatar or [])
    avatars = [path for path in sorted(root.iterdir()) if path.is_dir() and (path / "manifest.json").is_file()]
    if selected:
        avatars = [path for path in avatars if path.name in selected]
        missing = selected - {path.name for path in avatars}
        if missing:
            raise SystemExit(f"Unbekannter Avatar: {', '.join(sorted(missing))}")
    if not avatars:
        raise SystemExit("Keine Avatar-Sätze gefunden")

    pages = args.output / "pages"
    if pages.exists():
        shutil.rmtree(pages)
    entries = []
    for avatar in avatars:
        name, version = validate(avatar)
        relative = Path(name) / f"v{version}" / f"{name}-v{version}.tar.gz"
        target = pages / relative
        bundle(avatar, target)
        digest = sha256(target)
        (target.parent / f"{target.name}.sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
        entries.append({"name": name, "version": version, "url": str(relative), "sha256": digest})
        print(f"OK {name} v{version}: {target} ({digest})")
    (pages / "index.json").write_text(json.dumps({"avatars": entries}, indent=2) + "\n", encoding="utf-8")
    links = "\n".join(f'<li><a href="{entry["url"]}">{entry["name"]} v{entry["version"]}</a></li>' for entry in entries)
    (pages / "index.html").write_text(f"<!doctype html><meta charset=utf-8><title>VIRIDIS Avatar Bundles</title><h1>VIRIDIS Avatar Bundles</h1><ul>{links}</ul>\n", encoding="utf-8")

if __name__ == "__main__":
    main()
