# Avatar-Ebenen: mia

Dritter Ebenensatz neben `hani` und `neo`. Der Renderer liest ausschliesslich
`manifest.json`; dieser Ordner laesst sich vollstaendig ersetzen, ohne dass am
Code etwas geaendert werden muss.

## Aufbau

| Datei | Bedeutung |
|---|---|
| `base.png` | Das Gesicht. Darueber liegt in jedem Frame genau eine Mundebene. |
| `portrait.png` | Das stilisierte Grundportrait. Grundlage fuer einen zweiten Lauf, wird beim Rendern nicht benutzt. |
| `mouth_X.png` … `mouth_H.png` | Die neun Viseme (Preston-Blair, wie Rhubarb sie ausgibt). `X` ist der Ruhemund. |
| `eyes_half.png`, `eyes_closed.png`, `eyes_wink_left.png` | Lidzustaende. Fuer offene Augen wird nichts gezeichnet — die sind in `base.png`. |
| `brows_<gefuehl>.png` | Brauenstellung je Gefuehl: neutral, happy, sad, surprised, angry, thinking, playful. |
| `profile_640.png` | Telegram-Profil-/Gruppenbild, 640x640, Kopf mittig im Kreis. |
| `profile_640_kreis-vorschau.png` | Kontrollbild mit rundem Ausschnitt; Scheitel und Kinn bleiben drin. |

## Wie der Satz entstanden ist

Nicht mit Pillow ins Gesicht gemalt — das war der erste, verworfene Versuch und
hinterliess Doppelkonturen und Retuscheflecken. Stattdessen der Weg von `hani`:
fuer jede Mundform, jeden Lidzustand und jede Braue zeichnet das Bildmodell das
**ganze** Portrait neu, immer aus demselben Grundbild. Aus der Differenz zum
Grundbild wird die veraenderte Region gewonnen.

Entscheidend dabei: **eine gemeinsame Region je Ebenengruppe.** Haette jede Ebene
ihre eigene Maske, schiene an deren weichem Rand das Grundbild durch und der Mund
wirkte aufgeklebt. So liegt in jedem Frame genau eine Zeichnung des Bereichs.

Jedes Rohbild wird vor dem Ausschneiden per Kreuzkorrelation auf das Grundbild
ausgerichtet; ausgewertet wird ein Ring ausserhalb des Gesichts, der sich nicht
aendern soll.

## Unterschied zu neo

Bei `neo` verdeckt die schwarze Sonnenbrille Augen und Brauen fast vollstaendig —
Blinzeln und Brauen-Emotionen sind technisch da, aber kaum sichtbar. Die Brille
hier ist durchsichtig, die Augen sind zu sehen: Lid- und Brauenanimation hat echte
Wirkung. Der Brillenrahmen bleibt bei Lidbewegung an seiner Stelle, weil die
Augenregion unterhalb des Rahmens endet.

## Emotionen: nur Brauen

 Auf Nachfrage entschieden (VIR-9): Emotionen bleiben `brows_only`. Der Renderer
kennt je Gefuehl nur eine Brauenebene; emotionale Mund- oder Wangenebenen haette
er nicht gelesen. `happy` und `playful` sind darum mit dem Ruhemund schwaecher
lesbar als mit einer eigenen Mundebene — das ist bewusst so und kein Fehler des
Satzes.

## Datenschutz

Die Vorlage zeigt eine reale Person und wurde ausschliesslich fuer diesen
Ebenensatz verwendet. Der fertige Avatar ist erkennbar eine Zeichnung und wird nie
als Mensch ausgegeben.
