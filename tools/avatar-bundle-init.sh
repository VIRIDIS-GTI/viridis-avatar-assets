#!/bin/sh
# Lädt einen versionierten Avatar-Bundle atomar beim ersten Start. Ohne URL bleibt
# der bisherige AVATAR_ASSETS_DIR-Mechanismus unverändert.
set -eu

url="${AVATAR_BUNDLE_URL:-}"
assets_dir="${AVATAR_ASSETS_DIR:-}"
checksum="${AVATAR_BUNDLE_SHA256:-}"

[ -n "$url" ] || exec "$@"
case "$url" in https://*) ;; *) echo "AVATAR_BUNDLE_URL muss https verwenden: $url" >&2; exit 64 ;; esac
[ -n "$assets_dir" ] || { echo "AVATAR_ASSETS_DIR fehlt bei gesetzter AVATAR_BUNDLE_URL" >&2; exit 64; }

# Ein bereits vollständig installierter Satz ist der erfolgreiche Zustand. Kein
# Netzwerkzugriff bei nachfolgenden Containerstarts, auch wenn der Anbieter ausfällt.
[ -f "$assets_dir/manifest.json" ] && exec "$@"

parent=$(dirname "$assets_dir")
name=$(basename "$assets_dir")
mkdir -p "$parent"
tmp=$(mktemp -d "$parent/.${name}.download.XXXXXX")
lock="$parent/.${name}.install.lock"
cleanup() { rm -rf "$tmp"; rmdir "$lock" 2>/dev/null || true; }
# EXIT feuert nicht vor einem exec; jeder Ausstieg raeumt darum ausdruecklich auf.
trap cleanup INT TERM
finish() { cleanup; exec "$@"; }
fail() {
  status=$1
  shift
  if [ $# -gt 0 ]; then echo "$*" >&2; fi
  cleanup
  exit "$status"
}

curl --fail --show-error --silent --location --proto '=https' --tlsv1.2 \
  --connect-timeout 15 --retry 3 --retry-delay 2 --max-time 180 \
  "$url" -o "$tmp/bundle.tar.gz" ||
  fail 66 "Avatar-Bundle nicht ladbar: $url"
if [ -n "$checksum" ]; then
  echo "$checksum  $tmp/bundle.tar.gz" | sha256sum -c - || fail 65
fi
# Verhindert Pfadtraversal und Geräte-/Symlink-Einträge im Archiv.
tar -tzf "$tmp/bundle.tar.gz" | grep -Eq '(^/|(^|/)\.\.(/|$))' &&
  fail 65 "Avatar-Bundle enthält einen unsicheren Pfad"
mkdir "$tmp/extracted"
tar -xzf "$tmp/bundle.tar.gz" -C "$tmp/extracted" --no-same-owner --no-same-permissions ||
  fail 65 "Avatar-Bundle liess sich nicht entpacken"
[ -f "$tmp/extracted/manifest.json" ] || fail 65 "Avatar-Bundle enthält kein manifest.json"
python3 - "$tmp/extracted/manifest.json" <<'PY' || fail 65
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    manifest = json.load(fh)
if not isinstance(manifest.get("name"), str) or not isinstance(manifest.get("version"), int):
    raise SystemExit("Avatar-Bundle enthält kein gültiges Manifest")
PY
# mkdir dient als atomare Sperre. Ohne sie wuerde mv ein zweites Archiv in ein
# inzwischen entstandenes Zielverzeichnis hineinverschieben.
if mkdir "$lock" 2>/dev/null; then
  if [ ! -e "$assets_dir" ] && mv "$tmp/extracted" "$assets_dir"; then
    echo "Avatar-Bundle installiert: $url -> $assets_dir"
  elif [ -f "$assets_dir/manifest.json" ]; then
    echo "Avatar-Satz war bereits installiert: $assets_dir"
  else
    fail 1 "Avatar-Bundle konnte nicht atomar installiert werden"
  fi
elif [ -f "$assets_dir/manifest.json" ]; then
  echo "Avatar-Satz war bereits installiert: $assets_dir"
else
  fail 1 "Avatar-Bundle-Installation ist bereits aktiv: $assets_dir"
fi
finish "$@"
