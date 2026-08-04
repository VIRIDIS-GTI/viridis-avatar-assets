#!/usr/bin/env python3
"""build_avatar.py — aus einem Personenfoto ein Avatar-Rig bauen.

    build_avatar.py --photo hani.jpg --name hani --out assets/avatar

Das Ergebnis ist ein Verzeichnis aus PNG-Ebenen und einer manifest.json. Wer die
Ebenen spaeter von Hand oder mit einem anderen Bildmodell ersetzen will, kann das —
der Renderer liest ausschliesslich das Manifest, nicht diesen Code.

------------------------------------------------------------------------------------
DIE VIER SCHRITTE

  1. AUFBEREITEN   Foto -> Landmarks -> waagerecht drehen, auf das Gesicht
                   zuschneiden, so einrahmen, dass der Kopf in den Kreis passt.
  2. STILISIEREN   aufbereitetes Foto -> Bildmodell -> Comic-Portraet.
  3. RIG           Landmarks auf dem Portraet -> Ebenen ausschneiden:
                   Viseme, Augenzustaende, Brauen je Gefuehl.
  4. MANIFEST      Ankerpunkte, Versaetze, Zuordnungen, dazu eine README.

------------------------------------------------------------------------------------
WARUM DER KREIS DIE EINRAHMUNG BESTIMMT

Telegram zeigt Videonachrichten RUND. Vom quadratischen Bild bleibt der
einbeschriebene Kreis uebrig, die Ecken fallen weg — das sind 21 % der Flaeche. Ein
Kopf, der das Quadrat gut ausfuellt, verliert im Kreis Scheitel und Kinn.

Deshalb rechnet die Einrahmung nicht in Bildkanten, sondern in diesem Kreis: der
gesamte Kopf plus ein Sicherheitsabstand muss hineinpassen, und weil der Kopf sich
spaeter noch bewegt (Nicken, Wackeln), kommt der Weg dieser Bewegung oben drauf.
Siehe HEAD_MOTION_MARGIN.

------------------------------------------------------------------------------------
WARUM DIE VISEME MASKIERT ERZEUGT WERDEN

Ein Mund, der nur verzerrt wird, bleibt geschlossen — er wird ein
auseinandergezogener geschlossener Mund, ohne Zaehne, ohne Mundinneres. Fuer die
weit offenen Viseme (D, C) sieht das falsch aus.

Die Bild-API kann mit einer Maske arbeiten und dann NUR den Mundbereich neu malen.
Alles ausserhalb der Maske bleibt Pixel fuer Pixel gleich — die Identitaetsdrift, die
eine vollstaendige Neuerzeugung je Viseme haette, ist damit ausgeschlossen, nicht
bloss unwahrscheinlich.

Ohne API-Zugang faellt das Verfahren auf Verzerrung zurueck (--mouth-mode warp). Das
funktioniert, sieht bei den offenen Visemen aber deutlich schlechter aus, und das
Skript sagt es dann auch.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ------------------------------------------------------------------------------------
# Konstanten

CANVAS = 1024               # Kantenlaenge der erzeugten Ebenen
FACE_CENTER_Y = 0.47        # wo die Kopfmitte sitzt, Anteil der Hoehe

# Kopfhoehe als Anteil der Kantenlaenge. Hergeleitet, nicht geraten:
#
#   Ein Kopf ist etwa 0,75-mal so breit wie hoch. Seine halbe Diagonale ist damit
#       sqrt((h/2)² + (0,75h/2)²) = 0,625 h
#   und genau die muss in den Kreis passen, abzueglich der Bewegungsreserve:
#       0,625 h ≤ r · (1 − HEAD_MOTION_MARGIN)   mit r = Kante/2
#   ergibt h ≤ 0,69 · Kante. Mit etwas Sicherheitsabstand: 0,62.
#
# 0,62 fuellte rund drei Viertel des Kreisradius — rechnerisch sauber, im Ergebnis
# aber zu zaghaft: im fertigen Video stand oben ein breiter Streifen Hintergrund,
# waehrend die Schultern unten am Rand anlagen. 0,70 fuellt 85 % und laesst dem
# Scheitel trotzdem Abstand; erst ab 0,78 ist die Bewegungsreserve rechnerisch
# aufgebraucht und das Nicken wuerde den Rand streifen.
HEAD_HEIGHT_FRACTION = 0.70
HEAD_MOTION_MARGIN = 0.08   # Reserve fuer Nicken und Wackeln, Anteil des Radius

# Preston-Blair, wie Rhubarb sie ausgibt. Die Faktoren beschreiben die Mundform
# relativ zum Ruhemund: (Breite, Hoehe, Rundung). Sie steuern sowohl die Verzerrung
# als auch die Formulierung fuer das Bildmodell.
VISEMES: dict[str, dict] = {
    "X": {"w": 1.00, "h": 0.20, "desc": "relaxed closed mouth at rest, lips gently together"},
    "A": {"w": 1.00, "h": 0.12, "desc": "lips pressed firmly together, as in the sounds M, B, P"},
    "B": {"w": 1.05, "h": 0.38, "desc": "slightly open mouth, teeth nearly closed and visible, as in EE, S, T"},
    "C": {"w": 1.05, "h": 0.62, "desc": "open mouth showing upper teeth and a little of the dark mouth interior, as in EH"},
    "D": {"w": 0.95, "h": 1.00, "desc": "wide open mouth, dark mouth interior clearly visible, as in AA, AH"},
    "E": {"w": 0.78, "h": 0.65, "desc": "rounded open mouth, oval shape, as in OH, ER"},
    "F": {"w": 0.55, "h": 0.50, "desc": "small puckered rounded mouth, lips pushed forward, as in OO, W"},
    "G": {"w": 0.95, "h": 0.32, "desc": "upper teeth resting on the lower lip, as in F, V"},
    "H": {"w": 0.90, "h": 0.58, "desc": "open mouth with the tongue tip raised behind the upper teeth, as in L"},
}

EMOTIONS = ["neutral", "happy", "sad", "surprised", "angry", "thinking", "playful"]

# Wie die Brauen je Gefuehl verschoben werden: (Hebung in Anteilen der Brauenhoehe,
# Neigung in Grad, innen/aussen). Positiv = nach oben.
BROW_POSES: dict[str, dict] = {
    "neutral":   {"lift": 0.00, "tilt": 0.0,  "asym": 0.0},
    "happy":     {"lift": 0.18, "tilt": 2.0,  "asym": 0.0},
    "sad":       {"lift": -0.05, "tilt": -9.0, "asym": 0.0},
    "surprised": {"lift": 0.55, "tilt": 3.0,  "asym": 0.0},
    "angry":     {"lift": -0.22, "tilt": 12.0, "asym": 0.0},
    "thinking":  {"lift": 0.20, "tilt": -3.0, "asym": 0.45},
    "playful":   {"lift": 0.30, "tilt": 4.0,  "asym": 0.60},
}

EYE_STATES = ["open", "half", "closed", "wink_left"]

# MediaPipe FaceMesh, die Punkte die hier gebraucht werden.
LM_EYE_L = [33, 133, 159, 145, 160, 158, 153, 144]      # aus Sicht des Bildes links
LM_EYE_R = [263, 362, 386, 374, 387, 385, 380, 373]
LM_BROW_L = [70, 63, 105, 66, 107]
LM_BROW_R = [300, 293, 334, 296, 336]
LM_MOUTH_OUTER = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409,
                  291, 375, 321, 405, 314, 17, 84, 181, 91, 146]
LM_CHIN = 152
LM_FOREHEAD = 10


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def step(msg: str) -> None:
    print(f"\n>> {msg}", flush=True)


def die(msg: str) -> "None":
    print(f"\nFEHLER: {msg}", file=sys.stderr)
    raise SystemExit(1)


# ------------------------------------------------------------------------------------
# Landmarks


@dataclass
class Face:
    """Landmarks eines Gesichts in Pixelkoordinaten des zugehoerigen Bildes."""

    points: np.ndarray               # (468|478, 2)
    size: tuple[int, int]            # (Breite, Hoehe) des Bildes

    def p(self, idx: int) -> np.ndarray:
        return self.points[idx]

    def group(self, idxs: list[int]) -> np.ndarray:
        return self.points[idxs]

    def center(self, idxs: list[int]) -> np.ndarray:
        return self.group(idxs).mean(axis=0)

    @property
    def eye_l(self) -> np.ndarray:
        return self.center(LM_EYE_L)

    @property
    def eye_r(self) -> np.ndarray:
        return self.center(LM_EYE_R)

    @property
    def mouth_center(self) -> np.ndarray:
        return self.center(LM_MOUTH_OUTER)

    @property
    def roll_degrees(self) -> float:
        """Neigung der Augenlinie. Positiv = das Bild muss gegen den Uhrzeigersinn."""
        d = self.eye_r - self.eye_l
        return math.degrees(math.atan2(d[1], d[0]))

    def bbox(self, idxs: list[int] | None = None) -> tuple[float, float, float, float]:
        pts = self.points if idxs is None else self.group(idxs)
        return (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())


def detect_face(img: Image.Image, what: str = "Bild") -> Face:
    """Landmarks auf einem PIL-Bild. Das groesste Gesicht, falls mehrere.

    ⚠️ mediapipe 1.0 hat `mp.solutions.face_mesh` ENTFERNT. Hier laeuft die
    Tasks-API mit einem .task-Modell — dieselben 478 Punkte in derselben
    Reihenfolge, nur anders aufgerufen. Anleitungen mit `mp.solutions` sind veraltet.
    """
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision

    model = os.environ.get("MEDIAPIPE_FACE_MODEL", "/opt/avatar/face_landmarker.task")
    if not Path(model).exists():
        die(f"Landmark-Modell fehlt: {model}. Im Image liegt es unter /opt/avatar; "
            f"ausserhalb ueber MEDIAPIPE_FACE_MODEL einen Pfad angeben.")

    rgb = np.ascontiguousarray(np.asarray(img.convert("RGB"), dtype=np.uint8))
    options = mp_vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=model),
        running_mode=mp_vision.RunningMode.IMAGE,
        num_faces=4,
        min_face_detection_confidence=0.3,
    )
    with mp_vision.FaceLandmarker.create_from_options(options) as landmarker:
        res = landmarker.detect(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))

    if not res.face_landmarks:
        die(f"Im {what} ist kein Gesicht zu finden. Ein frontales, gut ausgeleuchtetes "
            f"Portraet funktioniert am besten.")

    h, w = rgb.shape[:2]
    faces = []
    for lm in res.face_landmarks:
        pts = np.array([[p.x * w, p.y * h] for p in lm], dtype=np.float64)
        area = (pts[:, 0].max() - pts[:, 0].min()) * (pts[:, 1].max() - pts[:, 1].min())
        faces.append((area, pts))

    if len(faces) > 1:
        log(f"{len(faces)} Gesichter gefunden — das groesste wird genommen, "
            f"die uebrigen fallen beim Zuschnitt weg.")
    faces.sort(key=lambda t: t[0], reverse=True)
    return Face(points=faces[0][1], size=(w, h))


# ------------------------------------------------------------------------------------
# Schritt 1: Aufbereiten


def background_color(img: Image.Image) -> tuple[int, int, int]:
    """Die Hintergrundfarbe, geschaetzt aus dem OBEREN Bildrand.

    Bewusst nicht aus allen vier Ecken: bei einem Portraet stehen unten die Schultern,
    und deren Kleidung faerbt den Median. Genau das ist einmal passiert — der
    fliederfarbene Hoodie machte aus einem cremefarbenen Hintergrund einen rosa Rand
    rund um das eingerahmte Bild.
    """
    a = np.asarray(img.convert("RGB"))
    h, w = a.shape[:2]
    k = max(4, min(h, w) // 40)
    strip = np.concatenate([
        a[:k, :].reshape(-1, 3),                 # oberer Rand
        a[:h // 3, :k].reshape(-1, 3),           # linke Flanke, oberes Drittel
        a[:h // 3, -k:].reshape(-1, 3),          # rechte Flanke, oberes Drittel
    ])
    return tuple(int(v) for v in np.median(strip, axis=0))


def crop_to_content(img: Image.Image, fill: tuple[int, int, int],
                    tol: int = 24) -> Image.Image:
    """Beschneidet mittig, bis keine Fuellfarbe mehr im Bild ist.

    Nach dem Drehen sitzen die Fuellreste in den Ecken. Ein gleichmaessiger Einzug
    von allen vier Seiten entfernt sie; wie tief, wird gesucht statt gerechnet — die
    Formel fuer das groesste einbeschriebene Rechteck haengt am Seitenverhaeltnis und
    ist hier den Aufwand nicht wert.
    """
    a = np.asarray(img.convert("RGB"), dtype=np.int16)
    bad = (np.abs(a - np.array(fill, dtype=np.int16)).max(axis=2) <= tol)
    if not bad.any():
        return img

    h, w = bad.shape
    lo, hi = 0, min(h, w) // 2 - 1
    while lo < hi:                                   # binaere Suche auf dem Einzug
        mid = (lo + hi) // 2
        if bad[mid:h - mid, mid:w - mid].any():
            lo = mid + 1
        else:
            hi = mid
    inset = lo
    log(f"Drehreste entfernt: {inset} px Einzug rundum "
        f"({w}×{h} -> {w - 2 * inset}×{h - 2 * inset}).")
    return img.crop((inset, inset, w - inset, h - inset))


def frame_for_circle(img: Image.Image, face: Face, canvas: int = CANVAS) -> Image.Image:
    """Dreht waagerecht und rahmt so ein, dass der Kopf in den Kreis passt.

    Der Bezug ist NICHT die Bildkante, sondern der einbeschriebene Kreis: Telegram
    zeigt Videonachrichten rund. Zusaetzlich bleibt HEAD_MOTION_MARGIN frei, damit
    Nicken und Wackeln spaeter nichts abschneiden.
    """
    bg = background_color(img)

    # 1. Waagerecht drehen — und die dabei entstehenden Ecken wieder wegschneiden.
    #
    # Drehen laesst an den vier Ecken Dreiecke aus Fuellfarbe zurueck. Bleiben die
    # stehen, zieht sich spaeter eine schraege Kante durch das fertige Bild: sichtbar
    # als Schnitt quer durch die Schultern. Deshalb wird nach dem Drehen auf den
    # groessten Ausschnitt beschnitten, der keine Fuellfarbe mehr enthaelt.
    #
    # Die Fuellfarbe ist bewusst ein Signalton, der in einem Portraet nicht vorkommt —
    # mit der Hintergrundfarbe zu fuellen waere bequemer, liesse sich hinterher aber
    # nicht mehr von echtem Hintergrund unterscheiden.
    roll = face.roll_degrees
    if abs(roll) > 0.5:
        log(f"Augenlinie ist {roll:+.1f}° geneigt — wird gerade gedreht.")
        sentinel = (255, 0, 255)
        rotated = img.convert("RGB").rotate(
            roll, resample=Image.BICUBIC, expand=True, fillcolor=sentinel)
        rotated = crop_to_content(rotated, sentinel)
        face = detect_face(rotated, "gedrehten Bild")
    else:
        rotated = img.convert("RGB")

    # 2. Kopfhoehe bestimmen. Die Landmarks enden an der Stirn (10), nicht am
    #    Haaransatz — der Schaedel darueber wird geschaetzt, sonst schneidet man
    #    zuverlaessig die Haare ab.
    chin = face.p(LM_CHIN)[1]
    brow = face.p(LM_FOREHEAD)[1]
    face_h = chin - brow
    head_top = brow - face_h * 0.62          # Schaetzung fuer Schaedeldach und Haar
    head_h = chin - head_top
    cx = float(face.center(LM_EYE_L + LM_EYE_R)[0])
    cy = float((chin + head_top) / 2.0)

    # 3. Massstab. HEAD_HEIGHT_FRACTION hat die Bewegungsreserve schon eingerechnet —
    #    sie hier ein zweites Mal abzuziehen, machte den Kopf halb so gross wie noetig.
    target_h = canvas * HEAD_HEIGHT_FRACTION
    scale = target_h / head_h
    log(f"Kopfhoehe {head_h:.0f} px -> {target_h:.0f} px (Faktor {scale:.3f}), "
        f"Kreisdurchmesser {canvas} px.")

    new_size = (max(1, int(round(rotated.width * scale))),
                max(1, int(round(rotated.height * scale))))
    scaled = rotated.resize(new_size, Image.LANCZOS)
    cx, cy = cx * scale, cy * scale

    # 4. Auf die Leinwand setzen, Kopfmitte auf FACE_CENTER_Y.
    out = Image.new("RGB", (canvas, canvas), bg)
    ox = int(round(canvas / 2 - cx))
    oy = int(round(canvas * FACE_CENTER_Y - cy))
    out.paste(scaled, (ox, oy))

    # 5. Unten fortsetzen. Ein Portraet ist an der Unterkante ABGESCHNITTEN — dort
    #    laufen Hals und Kleidung aus dem Bild. Bleibt darunter der Hintergrund
    #    stehen, zieht sich eine sichtbare Kante quer durch die Schultern. Also die
    #    unterste Bildzeile nach unten fortschreiben.
    #
    #    Nur unten: oben, links und rechts ist der Hintergrund die richtige Antwort,
    #    und ein Fortschreiben wuerde dort die Haare zu senkrechten Streifen ziehen.
    bottom = oy + scaled.height
    if 0 < bottom < canvas:
        last_row = out.crop((0, bottom - 1, canvas, bottom))
        out.paste(last_row.resize((canvas, canvas - bottom), Image.NEAREST),
                  (0, bottom))
    return out


def circle_fit_report(img: Image.Image) -> str:
    """Passt der Kopf in den Kreis? Wird als Zeile ins Protokoll geschrieben."""
    face = detect_face(img, "eingerahmten Bild")
    chin = face.p(LM_CHIN)[1]
    brow = face.p(LM_FOREHEAD)[1]
    top = brow - (chin - brow) * 0.62
    x0, _, x1, _ = face.bbox()
    r = img.width / 2.0
    cx = cy = r
    worst = 0.0
    for px, py in [(x0, top), (x1, top), (x0, chin), (x1, chin),
                   (cx, top), (cx, chin)]:
        worst = max(worst, math.hypot(px - cx, py - cy) / r)
    return (f"Kopf fuellt {worst * 100:.0f} % des Kreisradius"
            + ("" if worst < 0.95 else "  ⚠️ knapp — Bewegung koennte anschneiden"))


# ------------------------------------------------------------------------------------
# Schritt 2: Stilisieren


class ImageAPI:
    """Bild-Endpunkt, OpenAI-kompatibel (LiteLLM, Azure, OpenAI)."""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    @classmethod
    def from_env(cls) -> "ImageAPI | None":
        base = (os.environ.get("AVATAR_IMAGE_BASE_URL")
                or os.environ.get("LITELLM_BASE_URL")
                or os.environ.get("OPENAI_BASE_URL") or "")
        key = (os.environ.get("AVATAR_IMAGE_API_KEY")
               or os.environ.get("LITELLM_API_KEY")
               or os.environ.get("OPENAI_API_KEY") or "")
        model = os.environ.get("AVATAR_IMAGE_MODEL", "gpt-image-2")
        if not base or not key:
            return None
        return cls(base, key, model)

    def edit(self, image: Image.Image, prompt: str,
             mask: Image.Image | None = None, size: int = CANVAS) -> Image.Image:
        import io
        import requests

        def png(im: Image.Image, mode: str = "RGB") -> bytes:
            buf = io.BytesIO()
            im.convert(mode).save(buf, format="PNG")
            return buf.getvalue()

        files = {"image": ("image.png", png(image), "image/png")}
        if mask is not None:
            # Die API malt dort neu, wo die Maske DURCHSICHTIG ist.
            files["mask"] = ("mask.png", png(mask, "RGBA"), "image/png")

        # Wiederholen statt aufgeben. Der Endpunkt haengt in der Praxis oft an einem
        # Tunnel oder einer Portweiterleitung, und die reissen ab — ein Lauf ueber
        # neun Viseme dauert eine Viertelstunde, und ihn wegen einer abgebrochenen
        # Verbindung von vorn zu beginnen kostet echtes Geld. Der Zwischenspeicher
        # daneben sorgt dafuer, dass ein Neustart die fertigen Formen behaelt.
        import time as _t
        last = None
        for versuch in range(5):
            try:
                r = requests.post(
                    f"{self.base_url}/images/edits",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files=files,
                    data={"model": self.model, "prompt": prompt,
                          "size": f"{size}x{size}", "n": "1"},
                    timeout=600,
                )
            except requests.exceptions.RequestException as e:
                last = e
                wait = 5 * (versuch + 1)
                log(f"Verbindung zur Bild-API weg ({type(e).__name__}) — neuer Versuch in {wait}s")
                _t.sleep(wait)
                continue
            if r.status_code == 200:
                break
            if r.status_code in (429, 500, 502, 503, 504) and versuch < 4:
                wait = 5 * (versuch + 1)
                log(f"Bild-API HTTP {r.status_code} — neuer Versuch in {wait}s")
                _t.sleep(wait)
                continue
            die(f"Bild-API antwortete HTTP {r.status_code}: {r.text[:400]}")
        else:
            die(f"Bild-API nach fuenf Versuchen nicht erreichbar: {last}")

        data = r.json()["data"][0]
        if "b64_json" in data:
            raw = base64.b64decode(data["b64_json"])
        else:
            raw = requests.get(data["url"], timeout=300).content
        return Image.open(io.BytesIO(raw)).convert("RGB")


STYLE_PROMPT = (
    "Turn this photo into a friendly 2D cartoon avatar portrait, keeping the person "
    "clearly recognizable: same face shape, same eye colour, same hair colour and "
    "hairstyle, same clothing colour. Clean cartoon style with smooth shading and "
    "clear outlines. Keep the pose exactly as it is: facing the viewer, head upright, "
    "mouth CLOSED with relaxed lips, both eyes open. Keep the framing and the size of "
    "the head in the frame exactly as they are. Plain solid background, no text, "
    "only this one person."
)


def stylize_opencv(img: Image.Image) -> Image.Image:
    """Rueckfallweg ohne API: Kantenbetonung plus Farbvereinfachung.

    Das ist kein Comic, das ist ein Filter — und sieht auch so aus. Es steht hier,
    damit die Pipeline ohne Modellzugang durchlaeuft und man das Rig testen kann.
    """
    a = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    for _ in range(2):
        a = cv2.bilateralFilter(a, 9, 120, 120)
    quant = (a // 24) * 24
    gray = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                  cv2.THRESH_BINARY, 9, 9)
    out = cv2.bitwise_and(quant, quant, mask=edges)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))


# ------------------------------------------------------------------------------------
# Schritt 3: Rig


def feathered_mask(size: tuple[int, int], poly: np.ndarray,
                   feather: int) -> Image.Image:
    """Weiche Maske aus einem Polygon. Weiss = gehoert dazu."""
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in poly], fill=255)
    if feather > 0:
        m = m.filter(ImageFilter.GaussianBlur(feather))
    return m


def expand_poly(poly: np.ndarray, factor: float, extra: float = 0.0) -> np.ndarray:
    """Polygon um seinen Schwerpunkt aufblasen."""
    c = poly.mean(axis=0)
    out = c + (poly - c) * factor
    if extra:
        d = out - c
        n = np.linalg.norm(d, axis=1, keepdims=True)
        n[n == 0] = 1
        out = out + d / n * extra
    return out


def region_box(poly: np.ndarray, pad: float, canvas: int) -> tuple[int, int, int, int]:
    x0, y0 = poly[:, 0].min(), poly[:, 1].min()
    x1, y1 = poly[:, 0].max(), poly[:, 1].max()
    w, h = x1 - x0, y1 - y0
    return (max(0, int(x0 - w * pad)), max(0, int(y0 - h * pad)),
            min(canvas, int(x1 + w * pad)), min(canvas, int(y1 + h * pad)))


def cut_layer(base: Image.Image, box: tuple[int, int, int, int],
              mask: Image.Image) -> Image.Image:
    """Schneidet einen Bereich mit Alpha aus — das wird eine Ebene."""
    layer = base.convert("RGBA").crop(box)
    layer.putalpha(mask.crop(box))
    return layer


def warp_mouth(patch: Image.Image, w_factor: float, h_factor: float) -> Image.Image:
    """Mundfleck stauchen/dehnen, Mitte bleibt Mitte."""
    w, h = patch.size
    nw, nh = max(1, int(w * w_factor)), max(1, int(h * h_factor))
    scaled = patch.resize((nw, nh), Image.LANCZOS)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(scaled, ((w - nw) // 2, (h - nh) // 2), scaled)
    return out


def close_eye(base: Image.Image, poly: np.ndarray, amount: float) -> Image.Image:
    """Augenlid: der Augenbereich wird gestaucht, darueber kommt Hautfarbe.

    amount 1.0 = ganz zu, 0.5 = halb. Das ist bewusst kein generativer Schritt: ein
    geschlossenes Auge ist geometrisch einfach, und ein Modell wuerde hier nur
    Flackern zwischen den Frames hinzufuegen.
    """
    x0, y0, x1, y1 = region_box(poly, 0.55, base.width)
    patch = base.convert("RGBA").crop((x0, y0, x1, y1))
    pw, ph = patch.size

    # Hautfarbe von oberhalb des Auges nehmen.
    skin_y = max(0, y0 - int(ph * 0.35))
    skin = base.convert("RGB").crop((x0, skin_y, x1, skin_y + max(2, ph // 4)))
    skin_col = tuple(int(v) for v in np.asarray(skin).reshape(-1, 3).mean(axis=0))

    keep = max(1, int(ph * (1.0 - 0.82 * amount)))
    squashed = patch.resize((pw, keep), Image.LANCZOS)

    out = Image.new("RGBA", (pw, ph), skin_col + (255,))
    eye_c = float(poly[:, 1].mean()) - y0
    top = int(np.clip(eye_c - keep / 2 + ph * 0.10 * amount, 0, ph - keep))
    out.paste(squashed, (0, top), squashed)

    if amount > 0.75:                        # Wimpernstrich beim geschlossenen Auge
        d = ImageDraw.Draw(out)
        ly = top + keep // 2
        d.line([(int(pw * 0.16), ly), (int(pw * 0.84), ly)],
               fill=(70, 50, 45, 210), width=max(2, ph // 26))

    mask = feathered_mask(base.size, expand_poly(poly, 1.75, base.width * 0.006),
                          feather=max(2, base.width // 190))
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(out, (x0, y0))
    layer.putalpha(mask)
    return layer


def pose_brows(base: Image.Image, face: Face, pose: dict) -> Image.Image:
    """Brauen versetzen und neigen — je Gefuehl eine Ebene."""
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    brows = [(LM_BROW_L, +1.0), (LM_BROW_R, -1.0)]

    for i, (idxs, side) in enumerate(brows):
        poly = expand_poly(face.group(idxs), 1.9, base.width * 0.012)
        x0, y0, x1, y1 = region_box(poly, 0.5, base.width)
        mask = feathered_mask(base.size, poly, feather=max(2, base.width // 150))
        patch = cut_layer(base, (x0, y0, x1, y1), mask)

        h = y1 - y0
        lift = pose["lift"] * (1.0 + (pose["asym"] if i == 0 else -pose["asym"]))
        dy = -lift * h * 0.55
        tilt = pose["tilt"] * side
        if abs(tilt) > 0.1:
            patch = patch.rotate(tilt, resample=Image.BICUBIC, expand=False)
        layer.alpha_composite(patch, (x0, int(round(y0 + dy))))

    return layer


def inpaint_region(base: Image.Image, poly: np.ndarray) -> Image.Image:
    """Bereich mit der Umgebung zumalen — fuer die Basisebene unter dem Mund."""
    a = cv2.cvtColor(np.asarray(base.convert("RGB")), cv2.COLOR_RGB2BGR)
    m = np.zeros(a.shape[:2], dtype=np.uint8)
    cv2.fillPoly(m, [expand_poly(poly, 1.25).astype(np.int32)], 255)
    out = cv2.inpaint(a, m, 9, cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))


MOUTH_PROMPT = (
    "Change ONLY the mouth of this cartoon portrait so that it shows {desc}. "
    "Keep the drawing style, the lip colour, the skin tone and the position of the "
    "mouth exactly as they are. Do not change anything else in the picture."
)


def build_mouths(portrait: Image.Image, face: Face, api: "ImageAPI | None",
                 mode: str, out_dir: Path) -> dict:
    """Die neun Viseme als Ebenen. Liefert den Manifest-Abschnitt."""
    poly = face.group(LM_MOUTH_OUTER)
    region = expand_poly(poly, 1.85, portrait.width * 0.012)
    box = region_box(region, 0.45, portrait.width)

    # Der weiche Rand ist breit, und zwar aus einem gemessenen Grund: das Bildmodell
    # trifft den Hautton im neu gemalten Bereich nicht exakt. Bei schmalem Rand
    # zeichnet dieser Unterschied eine feine waagerechte Naht quer ueber die
    # Oberlippe — im fertigen Video als zuckender Strich sichtbar, sobald der Mund
    # wechselt. Ein breiter Verlauf blendet die Abweichung unter die Wahrnehmung.
    mask = feathered_mask(portrait.size, region,
                          feather=max(6, portrait.width // 55))

    generative = mode == "generative" and api is not None
    if mode == "generative" and api is None:
        log("⚠️  Kein Bildmodell erreichbar — die Viseme entstehen durch Verzerrung. "
            "Die offenen Formen (C, D) sehen damit deutlich schlechter aus.")

    # Die Maske fuer die API: durchsichtig dort, wo neu gemalt werden soll.
    api_mask = Image.new("RGBA", portrait.size, (255, 255, 255, 255))
    hole = feathered_mask(portrait.size, region, feather=0)
    api_mask.putalpha(Image.eval(hole, lambda v: 255 - v))

    # Die Modellantworten werden abgelegt. Ein Aufruf dauert rund zwei Minuten und
    # kostet Geld; wer hinterher nur am Zuschnitt oder am weichen Rand dreht, soll
    # dafuer nicht neu bezahlen muessen.
    #
    # ⚠️ Der Name traegt den Fingerabdruck des PORTRAETS, nicht nur den des Visems.
    # Ohne das passiert Folgendes, und es ist einmal passiert: ein zweiter Lauf mit
    # anders eingerahmtem Gesicht findet `A.png` aus dem alten Lauf, haelt es fuer
    # gueltig und klebt einen Mund an die Stelle, an der der Mund frueher war. Das
    # Ergebnis sind neun Gesichter mit einem Fleck neben dem Kinn.
    import hashlib as _h
    fp = _h.sha256(portrait.tobytes()).hexdigest()[:12]
    cache = out_dir / "_edits"
    cache.mkdir(exist_ok=True)
    for stale in cache.glob("*.png"):
        if not stale.name.startswith(fp):
            stale.unlink()
            log(f"Zwischenspeicher verworfen (anderes Portraet): {stale.name}")

    entries = {}
    for name, spec in VISEMES.items():
        if generative and name not in ("X",):
            cached = cache / f"{fp}-{name}.png"
            if cached.exists():
                edited = Image.open(cached).convert("RGB")
                log(f"Viseme {name}: aus {cached.name} wiederverwendet")
            else:
                edited = api.edit(portrait, MOUTH_PROMPT.format(desc=spec["desc"]),
                                  mask=api_mask)
                if edited.size != portrait.size:
                    edited = edited.resize(portrait.size, Image.LANCZOS)
                edited.save(cached)
            layer = cut_layer(edited, box, mask)
        else:
            patch = cut_layer(portrait, box, mask)
            layer = warp_mouth(patch, spec["w"], spec["h"]) if name != "X" else patch

        fn = f"mouth_{name}.png"
        layer.save(out_dir / fn)
        entries[name] = {"file": fn, "offset": [box[0], box[1]]}
        log(f"Viseme {name}: {fn}")

    return {
        "layers": entries,
        "anchor": [float(face.mouth_center[0]), float(face.mouth_center[1])],
        "mode": "generative" if generative else "warp",
    }


# ------------------------------------------------------------------------------------
# Manifest und README


ASSET_README = """# Avatar-Ebenen: {name}

Erzeugt von `build_avatar.py` am {date}. Der Renderer liest ausschliesslich
`manifest.json` — dieser Ordner laesst sich vollstaendig von Hand ersetzen, ohne dass
am Code etwas geaendert werden muss.

## Aufbau

| Datei | Bedeutung |
|---|---|
| `base.png` | Das Gesicht. Augen offen, Mundbereich leer — darueber liegt immer eine Mundebene. |
| `portrait.png` | Das unveraenderte Comic-Portraet. Grundlage fuer einen zweiten Lauf, wird beim Rendern nicht benutzt. |
| `mouth_X.png` … `mouth_H.png` | Die neun Viseme (Preston-Blair, wie Rhubarb sie ausgibt). `X` ist der Ruhemund. |
| `eyes_half.png`, `eyes_closed.png`, `eyes_wink_left.png` | Lidzustaende. Fuer offene Augen wird nichts gezeichnet — die sind in `base.png`. |
| `brows_<gefuehl>.png` | Brauenstellung je Gefuehl: {emotions}. |

## Eine Ebene austauschen

Datei mit gleichem Namen und gleicher Groesse ueberschreiben. Der Versatz steht im
Manifest unter `offset` und ist die linke obere Ecke auf der Leinwand ({canvas}×{canvas}).
Wer eine Ebene an anderer Stelle haben will, aendert dort den Versatz — nicht das Bild.

Alle Ebenen sind PNG mit Alphakanal. Die weichen Raender sind Absicht: eine harte
Kante zeichnet beim Zusammensetzen eine sichtbare Naht.

## Was der Kreis damit zu tun hat

Telegram zeigt Videonachrichten rund; vom Quadrat bleibt der einbeschriebene Kreis.
Die Einrahmung ist darauf gerechnet, mit Reserve fuer Kopfbewegung. Wer `base.png`
gegen ein eigenes Bild tauscht, sollte den Kopf deshalb **nicht** bis an die Bildkante
setzen — im fertigen Video waeren Scheitel und Kinn ab.

{fit}
"""


def write_manifest(out_dir: Path, name: str, portrait: Image.Image, face: Face,
                   mouths: dict, eyes: dict, brows: dict, fit: str,
                   source: dict) -> None:
    import datetime

    manifest = {
        "name": name,
        "version": 1,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "canvas": {"width": portrait.width, "height": portrait.height},
        # Fuer Telegram-Videonachrichten: alles Wichtige liegt im Kreis.
        "safe_circle": {"cx": portrait.width / 2, "cy": portrait.height / 2,
                        "r": portrait.width / 2},
        "base": "base.png",
        "portrait": "portrait.png",
        "anchors": {
            "eye_left": [float(face.eye_l[0]), float(face.eye_l[1])],
            "eye_right": [float(face.eye_r[0]), float(face.eye_r[1])],
            "mouth": [float(face.mouth_center[0]), float(face.mouth_center[1])],
            "head_center": [portrait.width / 2, portrait.height * FACE_CENTER_Y],
        },
        "visemes": mouths,
        "eyes": eyes,
        "brows": brows,
        "emotions": EMOTIONS,
        "source": source,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    (out_dir / "README.md").write_text(ASSET_README.format(
        name=name, date=manifest["created"], emotions=", ".join(EMOTIONS),
        canvas=portrait.width, fit=fit), encoding="utf-8")


# ------------------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Aus einem Personenfoto ein Avatar-Rig bauen.")
    ap.add_argument("--photo", type=Path, help="Ausgangsfoto")
    ap.add_argument("--name", required=True, help="Name des Avatars, z. B. hani")
    ap.add_argument("--out", type=Path, default=Path("assets/avatar"),
                    help="Zielverzeichnis, darunter entsteht <name>/")
    ap.add_argument("--from-portrait", type=Path,
                    help="Fertiges Comic-Portraet benutzen statt neu zu erzeugen")
    ap.add_argument("--reframe", action="store_true",
                    help="Auch ein fertiges Portraet neu einrahmen (Kreis, Bewegungsreserve)")
    ap.add_argument("--mouth-mode", choices=["generative", "warp"],
                    default="generative", help="Wie die Viseme entstehen")
    ap.add_argument("--stylizer", choices=["api", "opencv", "none"], default="api")
    args = ap.parse_args()

    if not args.photo and not args.from_portrait:
        die("Entweder --photo oder --from-portrait angeben.")

    out_dir = args.out / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    api = ImageAPI.from_env()
    source: dict = {"name": args.name}

    # --- Portraet beschaffen -------------------------------------------------
    if args.from_portrait:
        step(f"Fertiges Portraet: {args.from_portrait}")
        portrait = Image.open(args.from_portrait).convert("RGB")
        source["portrait"] = str(args.from_portrait)
        if args.reframe:
            step("Neu einrahmen (Kreis + Bewegungsreserve)")
            portrait = frame_for_circle(portrait, detect_face(portrait, "Portraet"))
    else:
        step(f"Foto aufbereiten: {args.photo}")
        photo = Image.open(args.photo).convert("RGB")
        prepared = frame_for_circle(photo, detect_face(photo, "Foto"))
        prepared.save(out_dir / "prepared.png")
        source["photo"] = str(args.photo)

        step("Stilisieren")
        if args.stylizer == "api" and api:
            log(f"Bildmodell {api.model} an {api.base_url}")
            portrait = api.edit(prepared, STYLE_PROMPT)
            source["stylizer"] = api.model
        elif args.stylizer == "none":
            portrait = prepared
            source["stylizer"] = "none"
        else:
            log("⚠️  Kein Bildmodell erreichbar (AVATAR_IMAGE_BASE_URL / "
                "LITELLM_BASE_URL und der passende Schluessel fehlen).")
            log("⚠️  Es wird ein OpenCV-Filter benutzt. Das ist kein Comic, das ist "
                "ein Filter — fuer einen Funktionstest gut genug, fuer den Betrieb "
                "nicht.")
            portrait = stylize_opencv(prepared)
            source["stylizer"] = "opencv-fallback"

    if portrait.size != (CANVAS, CANVAS):
        portrait = portrait.resize((CANVAS, CANVAS), Image.LANCZOS)

    # Einrahmen kommt NACH dem Stilisieren, und zwar immer.
    #
    # Der naheliegende Weg — Foto einrahmen, dann stilisieren — funktioniert nicht:
    # das Bildmodell komponiert den Ausschnitt neu, ganz gleich wie die Eingabe
    # aussieht. Nachgemessen: eine Eingabe mit 635 px Kopfhoehe kam mit einem Kopf
    # zurueck, der 111 % des Kreisradius fuellte. Anweisungen im Prompt ("keep the
    # framing exactly") aendern daran nichts.
    #
    # Am Ende eingerahmt ist die Bedingung dagegen garantiert eingehalten, weil sie
    # gerechnet und nicht erbeten wird. Gedreht werden muss dabei nichts mehr — die
    # Vorlage war schon waagerecht —, also entstehen auch keine schiefen Kanten.
    if not (args.from_portrait and not args.reframe):
        step("Auf den Kreis einrahmen")
        portrait = frame_for_circle(portrait, detect_face(portrait, "Portraet"))

    portrait.save(out_dir / "portrait.png")

    # --- Rig ------------------------------------------------------------------
    step("Landmarks auf dem Portraet")
    face = detect_face(portrait, "Portraet")
    fit = circle_fit_report(portrait)
    log(fit)

    step("Basisebene (Mundbereich zugemalt)")
    base = inpaint_region(portrait, face.group(LM_MOUTH_OUTER))
    base.save(out_dir / "base.png")

    step(f"Viseme ({args.mouth_mode})")
    mouths = build_mouths(portrait, face, api, args.mouth_mode, out_dir)

    step("Augenzustaende")
    eyes = {"open": {"file": None}}
    for state, amount in (("half", 0.5), ("closed", 1.0)):
        layer = Image.new("RGBA", portrait.size, (0, 0, 0, 0))
        for idxs in (LM_EYE_L, LM_EYE_R):
            layer.alpha_composite(close_eye(portrait, face.group(idxs), amount))
        fn = f"eyes_{state}.png"
        layer.save(out_dir / fn)
        eyes[state] = {"file": fn, "offset": [0, 0]}
        log(fn)

    wink = close_eye(portrait, face.group(LM_EYE_L), 1.0)
    wink.save(out_dir / "eyes_wink_left.png")
    eyes["wink_left"] = {"file": "eyes_wink_left.png", "offset": [0, 0]}
    log("eyes_wink_left.png")

    step("Brauen je Gefuehl")
    brows = {}
    for emo in EMOTIONS:
        layer = pose_brows(portrait, face, BROW_POSES[emo])
        fn = f"brows_{emo}.png"
        layer.save(out_dir / fn)
        brows[emo] = {"file": fn, "offset": [0, 0]}
        log(fn)

    step("Manifest und README")
    write_manifest(out_dir, args.name, portrait, face, mouths, eyes, brows,
                   fit, source)

    print(f"\nFertig: {out_dir}")
    print(f"  {len(list(out_dir.glob('*.png')))} Ebenen, manifest.json, README.md")
    print(f"  {fit}")


if __name__ == "__main__":
    main()
