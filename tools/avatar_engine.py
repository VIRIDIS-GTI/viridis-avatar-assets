#!/usr/bin/env python3
"""avatar_engine.py — die drei Schichten des Avatar-Videos.

    AvatarEngine   render_frame(t, params) -> Bild
    Driver         liefert params ueber die Zeit
    Sink           nimmt den Frame-Strom ab

Die Trennung ist keine Zierde, sondern die Bedingung dafuer, dass aus dem
Datei-Weg (Videonachricht) spaeter ein Echtzeit-Weg (WebRTC) werden kann, ohne
dass am Zeichnen etwas geaendert werden muss.

------------------------------------------------------------------------------------
1. AvatarEngine

Eine reine Funktion von Parametern auf ein Bild. Sie kennt weder Audio noch Datei
noch Netzwerk — sie bekommt {viseme, emotion, intensity, eye_state, head_pose} und
setzt Ebenen zusammen. Dasselbe Parameterpaket ergibt immer dasselbe Frame, und das
ist der Grund, warum man den Renderer testen kann, ohne je eine WAV zu erzeugen.

2. Driver

MouthDriver liefert Viseme ueber die Zeit. RhubarbDriver liest eine fertige
Viseme-Spur; ein StreamingDriver koennte dieselbe Schnittstelle live bedienen
(Amplitude, TTS-Ereignisse) — `viseme_at(t)` ist alles, was die Engine braucht.

ExpressionDriver macht aus dem Regieblock des Modells Gefuehl und Gesten und legt
das Unwillkuerliche darueber: Blinzeln und leichtes Kopfwackeln. Ohne das wirkt ein
Gesicht tot, und zwar sofort — ein Mensch blinzelt alle drei bis fuenf Sekunden.

3. Sink

FileSink sammelt Frames und laesst ffmpeg daraus ein H.264-mp4 machen. Ein
WebRTCSink wuerde dieselben Frames an eine VideoStreamTrack geben; deshalb nimmt
`push(frame, t)` einen einzelnen Frame und keine Liste.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

# ------------------------------------------------------------------------------------

FPS = 25
SIZE = 512                      # Telegram-Videonachricht: quadratisch
MAX_SECONDS = 60                # laenger nimmt sendVideoNote nicht

EMOTIONS = ["neutral", "happy", "sad", "surprised", "angry", "thinking", "playful"]
VISEMES = list("XABCDEFGH")


@dataclass(frozen=True)
class Params:
    """Alles, was ein Frame bestimmt. Mehr braucht die Engine nicht zu wissen."""

    viseme: str = "X"
    emotion: str = "neutral"
    intensity: float = 0.0
    eye_state: str = "open"          # open | half | closed | wink_left
    head_pose: tuple[float, float, float] = (0.0, 0.0, 0.0)   # dx, dy, Grad


# ------------------------------------------------------------------------------------
# 1. AvatarEngine


class AvatarEngine:
    """Setzt aus den Ebenen des Manifests ein Frame zusammen.

    Kennt keine Zeit. `render_frame` bekommt t nur, damit die Signatur zum
    Echtzeit-Weg passt — benutzt wird ausschliesslich `params`.
    """

    def __init__(self, asset_dir: Path, size: int = SIZE):
        self.dir = Path(asset_dir)
        manifest_path = self.dir / "manifest.json"
        if not manifest_path.exists():
            raise SystemExit(f"Kein manifest.json in {self.dir}")
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.size = size
        self.canvas = (self.manifest["canvas"]["width"], self.manifest["canvas"]["height"])
        self._cache: dict[str, Image.Image] = {}

        self.base = self._load(self.manifest["base"])
        # Der Hintergrund wird gebraucht, sobald der Kopf sich bewegt: unter dem
        # verschobenen Bild darf keine Luecke stehen. Die Farbe kommt aus einer Ecke,
        # nicht aus der Mitte - dort ist Gesicht.
        self.bg = self.base.convert("RGB").getpixel((4, 4))

    def _load(self, name: str) -> Image.Image:
        if name not in self._cache:
            self._cache[name] = Image.open(self.dir / name).convert("RGBA")
        return self._cache[name]

    def _layer(self, entry: dict | None) -> tuple[Image.Image, tuple[int, int]] | None:
        if not entry or not entry.get("file"):
            return None
        return self._load(entry["file"]), tuple(entry.get("offset", [0, 0]))

    def render_frame(self, t: float, params: Params) -> Image.Image:
        frame = self.base.copy()

        # Mund. Immer eine Ebene - die Basis hat den Mundbereich zugemalt, damit
        # nicht zwei Muender uebereinander liegen.
        mouth = self._layer(self.manifest["visemes"]["layers"].get(
            params.viseme if params.viseme in self.manifest["visemes"]["layers"] else "X"))
        if mouth:
            frame.alpha_composite(mouth[0], mouth[1])

        # Brauen. Fuer neutral gibt es eine Ebene wie fuer jedes andere Gefuehl;
        # bei sehr kleiner Staerke bleibt sie weg, sonst zappelt das Gesicht.
        if params.intensity > 0.15:
            brow = self._layer(self.manifest["brows"].get(params.emotion))
            if brow:
                frame.alpha_composite(brow[0], brow[1])

        # Augen. "open" ist bewusst leer: die offenen Augen stehen in der Basis.
        eye = self._layer(self.manifest["eyes"].get(params.eye_state))
        if eye:
            frame.alpha_composite(eye[0], eye[1])

        # Kopfbewegung zuletzt, auf das fertige Gesicht - so wandert alles zusammen.
        dx, dy, rot = params.head_pose
        if dx or dy or rot:
            moved = Image.new("RGBA", frame.size, self.bg + (255,))
            src = frame.rotate(rot, resample=Image.BICUBIC, center=(
                frame.width / 2, frame.height * 0.62), fillcolor=self.bg + (255,))
            moved.paste(src, (int(round(dx)), int(round(dy))), src)
            frame = moved

        if frame.size != (self.size, self.size):
            frame = frame.resize((self.size, self.size), Image.LANCZOS)
        return frame.convert("RGB")


# ------------------------------------------------------------------------------------
# 2. Driver


class MouthDriver:
    """Viseme ueber die Zeit. Die Schnittstelle, an der spaeter Echtzeit andockt."""

    def viseme_at(self, t: float) -> str:
        raise NotImplementedError

    @property
    def duration(self) -> float:
        raise NotImplementedError


class RhubarbDriver(MouthDriver):
    """Liest die Viseme-Spur, die Rhubarb aus einer WAV erzeugt hat.

    Rhubarb liefert `mouthCues` mit start, end und value - genau die Preston-Blair-
    Buchstaben, unter denen auch die Ebenen liegen. Mehr ist hier nicht zu tun; die
    Arbeit steckt in der Aufbereitung der Assets.
    """

    def __init__(self, cues: list[dict]):
        self.cues = sorted(cues, key=lambda c: c["start"])
        self._dur = max((c["end"] for c in self.cues), default=0.0)

    @classmethod
    def from_wav(cls, wav: Path, extra_args: list[str] | None = None) -> "RhubarbDriver":
        """Viseme-Spur aus einer Sprachdatei.

        ⚠️ Die Datei wird VORHER auf mono/16 kHz gebracht, und das ist kein Luxus:
        Rhubarb meldet fuer eine 44,1-kHz-WAV `duration 0.00` und genau einen Cue `X`
        — es scheitert also, ohne zu scheitern. Der Exit-Code ist 0, die Ausgabe
        wohlgeformt, und das Ergebnis ist ein Video, in dem der Mund geschlossen
        bleibt, waehrend jemand spricht. Genau so ist es einmal durchgerutscht.

        Cartesia liefert von Haus aus 44,1 kHz. Wer hier etwas aendert, prueft die
        Dauer im Ergebnis, nicht den Rueckgabewert.
        """
        if not shutil.which("rhubarb"):
            raise SystemExit("rhubarb fehlt - im openclaw-base-Image liegt es unter "
                             "/usr/local/bin/rhubarb.")
        with tempfile.TemporaryDirectory() as tmp:
            norm = Path(tmp) / "rhubarb-in.wav"
            conv = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav),
                 "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(norm)],
                capture_output=True, text=True)
            if conv.returncode != 0 or not norm.exists():
                raise SystemExit(f"Konnte {wav} nicht nach mono/16 kHz wandeln: "
                                 f"{conv.stderr[:300]}")
            out = subprocess.run(
                ["rhubarb", "-f", "json", *(extra_args or []), str(norm)],
                capture_output=True, text=True)
            if out.returncode != 0:
                raise SystemExit(f"rhubarb scheiterte: {out.stderr[:300]}")
            data = json.loads(out.stdout)

        if float(data.get("metadata", {}).get("duration", 0)) <= 0:
            raise SystemExit(
                f"rhubarb meldet Dauer 0 fuer {wav} — die Spur waere leer und der Mund "
                f"bliebe im ganzen Video geschlossen. Abbruch statt stummer Ausgabe.")
        return cls(data["mouthCues"])

    @classmethod
    def from_json(cls, path: Path) -> "RhubarbDriver":
        return cls(json.loads(Path(path).read_text(encoding="utf-8"))["mouthCues"])

    def viseme_at(self, t: float) -> str:
        for c in self.cues:
            if c["start"] <= t < c["end"]:
                return c["value"]
        return "X"

    @property
    def duration(self) -> float:
        return self._dur


@dataclass
class Cue:
    """Eine Geste zu einem Zeitpunkt."""
    type: str            # wink | nod
    at: float            # Sekunden


class ExpressionDriver:
    """Gefuehl, Gesten und das Unwillkuerliche.

    Zwei Quellen kommen hier zusammen. Die eine ist der Regieblock des Modells:
    Abschnitte mit Gefuehl und Staerke, dazu Gesten an Wort- oder Satzgrenzen. Die
    andere ist das, was ein Gesicht ohnehin tut - blinzeln und sich leicht bewegen.

    Das Unwillkuerliche ist nicht Beiwerk. Ein Gesicht, das nur den Mund bewegt,
    wirkt sofort tot; ein Mensch blinzelt alle drei bis fuenf Sekunden und haelt den
    Kopf nie ganz still. Beides laeuft deshalb prozedural mit, unabhaengig davon, was
    das Modell geliefert hat.
    """

    BLINK_MIN, BLINK_MAX = 2.6, 5.4      # Abstand zwischen zwei Lidschlaegen
    BLINK_LEN = 0.13                     # so lange ist das Auge zu
    WINK_LEN = 0.30

    def __init__(self, segments: list[dict], cues: list[Cue], duration: float,
                 seed: int = 7):
        self.duration = duration
        self.cues = cues
        self.rng = random.Random(seed)    # fester Startwert = wiederholbares Video

        # Abschnitte auf die Zeitachse legen. Ohne Wort-Zeitstempel bleibt nur die
        # Laenge des Textes als Massstab - Sprechtempo ist ueber einen Absatz
        # hinweg erstaunlich gleichmaessig, das traegt fuer diesen Zweck.
        total = sum(max(len(s.get("text", "")), 1) for s in segments) or 1
        self.spans: list[tuple[float, float, str, float]] = []
        cursor = 0.0
        for s in segments:
            share = max(len(s.get("text", "")), 1) / total
            end = cursor + share * duration
            emo = s.get("emotion", "neutral")
            self.spans.append((cursor, end, emo if emo in EMOTIONS else "neutral",
                               float(s.get("intensity", 0.5))))
            cursor = end
        if not self.spans:
            self.spans = [(0.0, duration, "neutral", 0.3)]

        self.blinks = self._plan_blinks()

    def _plan_blinks(self) -> list[float]:
        out, t = [], self.rng.uniform(0.8, 2.0)
        while t < self.duration:
            out.append(t)
            t += self.rng.uniform(self.BLINK_MIN, self.BLINK_MAX)
        return out

    def emotion_at(self, t: float) -> tuple[str, float]:
        for start, end, emo, strength in self.spans:
            if start <= t < end:
                return emo, strength
        return self.spans[-1][2], self.spans[-1][3]

    def eye_at(self, t: float) -> str:
        for c in self.cues:
            if c.type == "wink" and c.at <= t < c.at + self.WINK_LEN:
                return "wink_left"
        for b in self.blinks:
            d = t - b
            if 0 <= d < self.BLINK_LEN:
                # halb - zu - halb, damit der Lidschlag nicht springt
                return "half" if d < 0.035 or d > self.BLINK_LEN - 0.035 else "closed"
        return "open"

    def head_at(self, t: float) -> tuple[float, float, float]:
        """Leichtes Wackeln, dazu ein Nicken auf Zuruf.

        Zwei Sinusse mit unrunden Frequenzen: bei glatten Vielfachen entsteht ein
        sichtbares Muster, und ein Kopf, der im Takt pendelt, sieht nach Maschine aus.
        """
        dx = 3.2 * math.sin(t * 0.83) + 1.4 * math.sin(t * 1.97 + 1.1)
        dy = 2.1 * math.sin(t * 0.61 + 0.4)
        rot = 0.8 * math.sin(t * 0.47 + 2.0)

        for c in self.cues:
            if c.type != "nod":
                continue
            d = t - c.at
            if 0 <= d < 0.62:
                # eine Halbwelle nach unten und zurueck
                dy += 13.0 * math.sin(math.pi * d / 0.62)
        return dx, dy, rot

    def params_at(self, t: float, viseme: str) -> Params:
        emo, strength = self.emotion_at(t)
        return Params(viseme=viseme, emotion=emo, intensity=strength,
                      eye_state=self.eye_at(t), head_pose=self.head_at(t))


# ------------------------------------------------------------------------------------
# 3. Sink


class Sink:
    def push(self, frame: Image.Image, t: float) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class FileSink(Sink):
    """Frames -> ffmpeg -> H.264-mp4, quadratisch, mit Ton.

    Die Frames gehen ueber eine Pipe an ffmpeg, nicht ueber tausend PNG auf die
    Platte: bei 25 fps und einer Minute waeren das 1500 Dateien, und der Umweg
    ueber das Dateisystem kostet mehr Zeit als das Kodieren.

    `-movflags +faststart` ist fuer Telegram nicht optional - ohne den Index am
    Anfang beginnt die Wiedergabe erst, wenn die Datei ganz geladen ist.
    """

    def __init__(self, out: Path, audio: Path | None, fps: int = FPS,
                 size: int = SIZE):
        self.out = Path(out)
        self.size = size
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{size}x{size}", "-r", str(fps), "-i", "pipe:0"]
        if audio:
            cmd += ["-i", str(audio)]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-profile:v", "baseline", "-level", "3.1"]
        if audio:
            cmd += ["-c:a", "aac", "-b:a", "96k", "-shortest"]
        cmd += ["-movflags", "+faststart", str(self.out)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
        self.count = 0

    def push(self, frame: Image.Image, t: float) -> None:
        if frame.size != (self.size, self.size):
            frame = frame.resize((self.size, self.size), Image.LANCZOS)
        self.proc.stdin.write(frame.convert("RGB").tobytes())
        self.count += 1

    def close(self) -> None:
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode("utf-8", "replace")
        if self.proc.wait() != 0:
            raise SystemExit(f"ffmpeg scheiterte: {err[:400]}")


# ------------------------------------------------------------------------------------
# Zusammenbau


def parse_cues(raw: list[dict], segments: list[dict], duration: float) -> list[Cue]:
    """`word:5` und `sentence:1` auf Sekunden umrechnen.

    Ohne Wort-Zeitstempel aus dem TTS bleibt nur der Text als Massstab. Das ist
    ungenau, aber die Ungenauigkeit faellt nicht auf: ein Zwinkern eine Zehntel
    Sekunde zu frueh sieht niemand, ein fehlendes Zwinkern schon.
    """
    text = " ".join(s.get("text", "") for s in segments)
    words = text.split()
    sentences = [s for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    out: list[Cue] = []
    for c in raw or []:
        at = c.get("at", "")
        kind = str(c.get("type", "")).lower()
        if kind not in ("wink", "nod"):
            continue
        try:
            unit, _, idx_s = str(at).partition(":")
            idx = int(idx_s)
        except ValueError:
            continue
        if unit == "word" and words:
            t = duration * min(idx, len(words) - 1) / max(len(words), 1)
        elif unit == "sentence" and sentences:
            spoken = " ".join(sentences[:idx])
            t = duration * len(spoken) / max(len(text), 1)
        else:
            continue
        out.append(Cue(type=kind, at=max(0.0, min(t, duration - 0.1))))
    return out


def render(assets: Path, spec: dict, audio: Path, out: Path,
           cues_json: Path | None = None, fps: int = FPS, size: int = SIZE,
           quiet: bool = False) -> dict:
    """Der Batch-Weg: Sprachdatei plus Regieblock -> Videonachricht."""
    engine = AvatarEngine(assets, size=size)

    mouth = (RhubarbDriver.from_json(cues_json) if cues_json
             else RhubarbDriver.from_wav(audio))
    duration = mouth.duration or _audio_duration(audio)
    if duration <= 0:
        raise SystemExit("Die Tonspur ist leer - ohne Dauer kein Video.")

    segments = spec.get("segments") or [{"text": spec.get("reply_text", ""),
                                         "emotion": "neutral", "intensity": 0.4}]
    expression = ExpressionDriver(segments, parse_cues(spec.get("cues"), segments, duration),
                                  duration)

    sink = FileSink(out, audio, fps=fps, size=size)
    frames = int(duration * fps) + 1
    for i in range(frames):
        t = i / fps
        sink.push(engine.render_frame(t, expression.params_at(t, mouth.viseme_at(t))), t)
        if not quiet and i % (fps * 5) == 0:
            print(f"  {t:5.1f}s / {duration:.1f}s", flush=True)
    sink.close()

    return {"file": str(out), "seconds": round(duration, 2), "frames": frames,
            "fps": fps, "size": size,
            "too_long": duration > MAX_SECONDS}


def _audio_duration(audio: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(audio)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar-Videonachricht rendern.")
    ap.add_argument("--assets", type=Path, required=True, help="Verzeichnis mit manifest.json")
    ap.add_argument("--audio", type=Path, required=True, help="WAV der Sprachausgabe")
    ap.add_argument("--spec", type=Path, help="Regieblock als JSON (segments, cues)")
    ap.add_argument("--cues", type=Path, help="fertige Rhubarb-Ausgabe statt neuem Lauf")
    ap.add_argument("--out", type=Path, default=Path("avatar.mp4"))
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--size", type=int, default=SIZE)
    args = ap.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8")) if args.spec else {}
    info = render(args.assets, spec, args.audio, args.out, cues_json=args.cues,
                  fps=args.fps, size=args.size)
    print(json.dumps(info, ensure_ascii=False))
    if info["too_long"]:
        print(f"⚠️  {info['seconds']} s — laenger als {MAX_SECONDS} s. Telegram nimmt das "
              f"nicht als Videonachricht; sendVideo (rechteckig) waere der Ausweg.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
