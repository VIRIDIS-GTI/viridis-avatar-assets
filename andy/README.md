# Avatar-Ebenen: andy

Gezeichneter Pop-Art-Avatar nach der Vorlage aus Task VIR-15 (`reference.jpg`,
Anhang am Paperclip-Task). Die Vorlage zeigt den Pop-Art-Look eines Kuenstlers
der 1960er: platinweisses, leicht zerzaustes Haar, **runde** schwarze Brille,
dunkles Jackett mit weissem Hemd und Krawatte, Duotone in Mintgruen auf Violett.
Der Satz ist eine Zeichnung, kein Foto.

| Datei | Zweck |
|---|---|
| `reference.jpg` | Vorlage aus dem Task, 800x800; wird nicht gerendert |
| `portrait.png` | gezeichnetes Quellportraet, 1024x1024; wird nicht gerendert |
| `base.png` | Gesicht mit ausgeraeumtem Mundbereich und gedaempften Originalbrauen |
| `mouth_X.png` … `mouth_H.png` | neun Viseme, 657x188 px |
| `eyes_half/closed/wink_left.png` | Lidzustaende; offene Augen stecken in `base.png` |
| `brows_<gefuehl>.png` | sieben Brauenebenen |
| `profile_640.png` | Telegram-Profil-/Gruppenbild, 640x640 |
| `profile_640_kreis-vorschau.png` | Kreis-Kontrollbild fuer Telegram |
| `static-render-check.png` | Standbild des Renderer-Tests |

Anker: Augen `[389,425]` und `[593,425]`, Mund `[508,620]`, Brauenlinie `y=373`.

**Mundebenen sind kieferverankert:** die Oberlippe bleibt auf fester Hoehe, der
Mund oeffnet nach unten. Ohne das rutscht der offene Mund sichtbar zu weit nach
oben.

Geprueft: alle 252 Ebenenkombinationen, Testvideo H.264/AAC 512x512 (1,2 s),
Kreisvorschau ohne Anschnitt von Scheitel und Kinn.
