# Avatar-Ebenen: andy

Originaler, gezeichneter Pop-Art-Avatar, sichtbar an die oeffentliche Bildpersona
von **Andy Warhol** angelehnt: platinweisses Haar, grosse schwarze Brille und
schwarzer Rollkragen. Er ist eine Illustration, kein Foto.

| Datei | Zweck |
|---|---|
| `portrait.png` | gezeichnetes Quellportraet, 1024x1024; wird nicht gerendert |
| `base.png` | Gesicht mit bereinigtem Mundbereich |
| `mouth_X.png` … `mouth_H.png` | neun Viseme, 657x188 px |
| `eyes_half/closed/wink_left.png` | Lidzustaende |
| `brows_<gefuehl>.png` | sieben Brauenebenen |
| `profile_640.png` | Telegram-Profil-/Gruppenbild, 640x640 |
| `profile_640_kreis-vorschau.png` | Kreis-Kontrollbild fuer Telegram |
| `static-render-check.png` | Standbild des Renderer-Tests |

Manifest-Anker: Augen `[412,457]` / `[589,457]`, Mund `[512,631]`.

Geprueft: alle 252 Ebenenkombinationen und ein H.264/AAC-Testvideo (512x512,
1,2 s). Im Kreis bleiben Scheitel und Kinn vollstaendig sichtbar.
