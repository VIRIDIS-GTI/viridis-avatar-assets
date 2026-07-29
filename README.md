# viridis-avatar-assets

Avatar-Ebenensaetze fuer die OpenClaw-Bots der VIRIDIS Green-Tech Investment AG.

Jeder Ordner ist ein vollstaendiger Satz, den der Avatar-Renderer direkt laden kann.
Die Bots ziehen ihn beim Start per initContainer in ihr Datenverzeichnis; der Pfad
steht dort in `AVATAR_ASSETS_DIR`.

## Saetze

| Satz | Figur | Verwendet von |
|---|---|---|
| `neo` | maennlich, kurze schwarze Haare, dunkle Sonnenbrille, schwarzer Mantel | VIRIDIS Dev Bot (`openclaw`) |
| `andy` | gezeichneter Pop-Art-Avatar, an Andy Warhol angelehnt | fuer einen weiteren OpenClaw-Bot vorbereitet |

Beide Saetze enthalten `profile_640.png` und die Kreis-Vorschau.

## Aufbau eines Satzes

| Datei | Zweck |
|---|---|
| `manifest.json` | Leinwandgroesse, Anker, Versaetze — der Renderer liest **nur** diese Datei |
| `base.png` | Gesicht ohne Mund; der Mundbereich ist ausgeraeumt |
| `portrait.png` | Vorlage, wird nicht gerendert |
| `mouth_X`, `mouth_A` … `mouth_H` | neun Viseme; `X` ist der geschlossene Mund |
| `eyes_half`, `eyes_closed`, `eyes_wink_left` | Lidzustaende; offene Augen stecken in `base.png` |
| `brows_<gefuehl>` | Brauen je Gefuehl: `neutral`, `happy`, `sad`, `surprised`, `angry`, `thinking`, `playful` |
| `profile_640.png` | Telegram-Profil-/Gruppenbild, 640x640, Kopf mittig im Kreis |
| `profile_640_kreis-vorschau.png` | Kontrollbild: derselbe Zuschnitt mit rundem Ausschnitt |
| `README.md` | Besonderheiten des Satzes |

Alle Ebenen sind PNG mit Alphakanal und teilen dieselbe Leinwandgroesse.

**Zu jedem Satz gehoert das Telegram-Bild.** Telegram zeigt Profil- und Gruppenbilder
rund; vom Quadrat bleibt der einbeschriebene Kreis. `profile_640.png` ist deshalb ein
Zuschnitt aus `portrait.png` mit dem Kopf in der Kreismitte, 640x640. Die
Kreis-Vorschau liegt daneben, damit sich der Zuschnitt pruefen laesst, ohne ihn
hochzuladen. Ein Satz ohne diese beiden Dateien ist unvollstaendig.

## Einen Satz einbinden

Der initContainer klont dieses Repo flach und kopiert einen Ordner:

```sh
git clone --depth 1 \
  "https://x-access-token:${GITHUB_CR_TOKEN}@github.com/VIRIDIS-GTI/viridis-avatar-assets.git" /src
cp -a /src/neo /out/neo
```

Ein Sparse-Checkout wie beim Infrastruktur-Repo ist hier nicht noetig — das Repo
enthaelt nichts anderes.

## Warum ein eigenes Repo

Die Saetze lagen zuerst im `infrastructure-monorepo` unter
`hetzner/k8s/apps/avatar-assets/`. Sie stehen dort weiterhin und sind der Stand, aus
dem dieses Repo entstanden ist.

Getrennt wurden sie, weil jeder weitere Bot sonst Lesezugriff auf die gesamte
Infrastruktur braucht, nur um sein Gesicht zu bekommen. Ein eigenes Repo laesst sich
einzeln freigeben.

## Datenschutz

Manche Saetze entstehen aus dem Portraet einer realen Person. Das Ergebnis ist
erkennbar eine Zeichnung und wird nie als Mensch ausgegeben. Vorlagenbilder gehoeren
nicht in dieses Repo — nur die fertigen Ebenen.
