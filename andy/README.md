# Avatar-Ebenen: andy

Vollstaendiger Satz fuer den OpenClaw-Avatar-Renderer. Die Vorlage ist eine
gezeichnete Figur; sie stellt keinen Menschen dar. Alle Animationsebenen und
Koordinaten stehen in `manifest.json`.

| Datei | Zweck |
|---|---|
| `portrait.png` | Quellportraet, 1024x1024, wird nicht gerendert |
| `base.png` | Gesicht mit ausgeraeumtem Mundbereich |
| `mouth_X.png` … `mouth_H.png` | neun Viseme, 657x188, Versatz `[189, 537]` |
| `eyes_half/closed/wink_left.png` | Lidzustaende; offene Augen stecken in `base.png` |
| `brows_<gefuehl>.png` | Brauen je Gefuehl |
| `profile_640.png` | Telegram-Profil-/Gruppenbild, 640x640 |
| `profile_640_kreis-vorschau.png` | Kontrollbild mit rundem Ausschnitt |
| `static-render-check.png` | Standbild aus dem Renderer-Test |

Anker: Augen `[545, 450]` und `[779, 450]`, Mund `[520, 620]`.

Geprueft: 252 Ebenen-Kombinationen im Renderer, dazu ein Testvideo
(H.264/AAC, 512x512, 1,2 s).
