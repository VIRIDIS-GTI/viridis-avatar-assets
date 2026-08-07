# Avatar-Ebenen: tank

Erzeugt von `build_avatar.py` am 2026-08-07T14:10:00. Der Renderer liest ausschliesslich
`manifest.json` — dieser Ordner laesst sich vollstaendig von Hand ersetzen, ohne dass
am Code etwas geaendert werden muss.

## Aufbau

| Datei | Bedeutung |
|---|---|
| `base.png` | Das Gesicht. Augen offen, Mundbereich leer — darueber liegt immer eine Mundebene. |
| `portrait.png` | Das unveraenderte Comic-Portraet. Grundlage fuer einen zweiten Lauf, wird beim Rendern nicht benutzt. |
| `mouth_X.png` … `mouth_H.png` | Die neun Viseme (Preston-Blair, wie Rhubarb sie ausgibt). `X` ist der Ruhemund. |
| `eyes_half.png`, `eyes_closed.png`, `eyes_wink_left.png` | Lidzustaende. Fuer offene Augen wird nichts gezeichnet — die sind in `base.png`. |
| `brows_<gefuehl>.png` | Brauenstellung je Gefuehl: neutral, happy, sad, surprised, angry, thinking, playful. |

## Eine Ebene austauschen

Datei mit gleichem Namen und gleicher Groesse ueberschreiben. Der Versatz steht im
Manifest unter `offset` und ist die linke obere Ecke auf der Leinwand (1024×1024).
Wer eine Ebene an anderer Stelle haben will, aendert dort den Versatz — nicht das Bild.

Alle Ebenen sind PNG mit Alphakanal. Die weichen Raender sind Absicht: eine harte
Kante zeichnet beim Zusammensetzen eine sichtbare Naht.

## Was der Kreis damit zu tun hat

Telegram zeigt Videonachrichten rund; vom Quadrat bleibt der einbeschriebene Kreis.
Die Einrahmung ist darauf gerechnet, mit Reserve fuer Kopfbewegung. Wer `base.png`
gegen ein eigenes Bild tauscht, sollte den Kopf deshalb **nicht** bis an die Bildkante
setzen — im fertigen Video waeren Scheitel und Kinn ab.

Kopf fuellt 87 % des Kreisradius
