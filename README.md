# VIRIDIS Avatar Assets

Versionierte Ebenensätze für die gezeichneten Video-Avatare der VIRIDIS Green-Tech
Investment AG. Der Renderer liest ausschließlich `manifest.json`; ein Satz ist damit
vollständig austauschbar, ohne den Renderer zu ändern.

## Sätze und Versionen

| Satz | Version | Öffentliche Bundle-URL | SHA-256 |
|---|---:|---|---|
| `hani` | 1 | `https://viridis-gti.github.io/viridis-avatar-assets/hani/v1/hani-v1.tar.gz` | `2885ae0eda94dc688c36155fe720a3ec5f825581c7508fc50c959cf4db19ee77` |
| `neo` | 1 | `https://viridis-gti.github.io/viridis-avatar-assets/neo/v1/neo-v1.tar.gz` | `e1ef17ba04b21cf470a39ab077f076eedc06201057ba1fe4aef9dafb31408ba7` |
| `andy` | 2 | `https://viridis-gti.github.io/viridis-avatar-assets/andy/v2/andy-v2.tar.gz` | `769c79dfe113f315ee9f9936f49b12b6ec127078e84917d8ce7592821a3040a9` |
| `mia` | 2 | `https://viridis-gti.github.io/viridis-avatar-assets/mia/v2/mia-v2.tar.gz` | `d23c1cc3e017746f4591a8945bd5403f131e62608083d4d5cca5fb2b7d0b8942` |
| `otto` | 1 | `https://viridis-gti.github.io/viridis-avatar-assets/otto/v1/otto-v1.tar.gz` | `99c174ba141150fa4d86754217c75947176b4d8d99c999942a0e496165362f87` |

Die URLs sind live; GitHub Pages ist für dieses Repository aktiv (Quelle: GitHub
Actions). Neben jedem Archiv liegt `<bundle>.sha256`, dazu ein Gesamtindex:

```sh
curl -sS https://viridis-gti.github.io/viridis-avatar-assets/index.json
```

Die Prüfsummen oben stammen aus diesem Index und sind identisch mit einem lokalen
`scripts/build_bundles.py`-Lauf — der Build ist bit-reproduzierbar.

**Versionskonvention:** `manifest.version` ist eine positive Ganzzahl je Satz. Eine
Änderung an gerenderten Ebenen oder Manifest-Verweisen erhöht sie. Der Pfad enthält
immer exakt `v<manifest.version>`; ältere Versionen bleiben als Referenz URLs stabil.

## Aufbau eines Satzes

| Datei | Zweck |
|---|---|
| `manifest.json` | Leinwand, Anker, Layer-Verweise — alleinige Renderer-Schnittstelle |
| `base.png` | Gesicht ohne animierten Mund |
| `portrait.png` | gezeichnete Vorlage, wird nicht gerendert |
| `mouth_X.png` bis `mouth_H.png` | neun Preston-Blair-Viseme |
| `eyes_half/closed/wink_left.png` | zusätzliche Lid-Zustände |
| `brows_<emotion>.png` | Brauen für sieben Emotionen |
| `profile_640.png` | Telegram-Profilbild, Kopf im Kreismittelpunkt |
| `profile_640_kreis-vorschau.png` | Prüfung des runden Telegram-Zuschnitts |

PNG-Layer haben eine gemeinsame Leinwand und einen Alphakanal. Ein Satz ohne
`profile_640.png` oder Kreisvorschau ist unvollständig.

## Reproduzierbar validieren und bündeln

Die komplette Build-/Bundle-Logik liegt absichtlich in diesem Repository:

```sh
python3 scripts/build_bundles.py --output dist
```

Der Lauf validiert Manifest, alle Pflichtlayer und Manifest-Verweise. Er erzeugt pro
Satz ein gzip-komprimiertes TAR inklusive SHA-256 und einen Pages-Index unter
`dist/pages/`. Für einen Einzeltest: `--avatar mia`.

Gzip-Zeitstempel und TAR-Metadaten sind festgeschrieben, darum ergibt derselbe Stand
bitgleiche Archive. Ein lokaler Lauf muss dieselben Prüfsummen liefern wie die
Tabelle oben; weicht eine ab, hat sich der Satzinhalt geändert und die Version gehört
erhöht.

Die GitHub Action `.github/workflows/deploy-pages.yml` führt exakt diesen Befehl bei
Push nach `main` aus, lädt das Ergebnis als Pages-Artefakt hoch und deployt es nach
GitHub Pages. Sie benötigt die Standardberechtigungen `pages: write` und `id-token:
write`; keine Registry- oder privaten Deploy-Schlüssel. Ein Lauf lässt sich ohne
Commit über `workflow_dispatch` auslösen.

## Verwendung im Container

`openclaw-base` verwendet `AVATAR_BUNDLE_URL` beim ersten Containerstart sicher und
atomar. Dazu gehören HTTPS-Zwang, Retry/Timeout, optionaler SHA-256-Vergleich,
Archiv-Pfadprüfung und Manifest-Validierung. Beispiel:

```yaml
- name: AVATAR_ASSETS_DIR
  value: /home/node/.openclaw/avatar/mia
- name: AVATAR_BUNDLE_URL
  value: https://viridis-gti.github.io/viridis-avatar-assets/mia/v2/mia-v2.tar.gz
- name: AVATAR_BUNDLE_SHA256
  value: d23c1cc3e017746f4591a8945bd5403f131e62608083d4d5cca5fb2b7d0b8942
```

Ohne `AVATAR_BUNDLE_URL` bleibt der bestehende InitContainer-/Git-Mechanismus
unverändert. Infrastruktur-Manifeste sollen künftig nur diese drei Werte je Bot
konfigurieren, nicht mehr Repo-Klone oder avatar-spezifische InitContainer enthalten.

Verhalten des Startpfads, jeder Fall gegen die obigen URLs getestet:

| Situation | Ergebnis |
|---|---|
| Satz liegt schon (`manifest.json` vorhanden) | kein Netzzugriff, Start läuft weiter |
| Erfolg | atomar installiert, Temp-Verzeichnis entfernt |
| Prüfsumme falsch | Abbruch 65, Ziel bleibt unangetastet |
| Download/TLS/404 fehlgeschlagen | Abbruch 66 |
| `AVATAR_BUNDLE_URL` nicht `https://` oder `AVATAR_ASSETS_DIR` fehlt | Abbruch 64 |
| Archiv mit absolutem Pfad oder `..` | Abbruch 65 |

`AVATAR_BUNDLE_SHA256` ist optional, aber empfohlen: nur damit ist ein untergeschobenes
Archiv ausgeschlossen.

## Avatar erzeugen oder ändern

Die komplette Generierungs- und Renderlogik liegt seit VIR-190 **in diesem
Repository** unter `tools/`. `openclaw-base` behält davon nur noch den
Laufzeit-Startpfad; es ist nicht mehr die Quelle des Generators.

| Datei | Zweck |
|---|---|
| `tools/build_avatar.py` | Generator: aus einer Vorlage einen vollständigen Ebenensatz samt `manifest.json` bauen |
| `tools/avatar_engine.py` | Renderer: Ebenen + Audio + Cues zum Video zusammensetzen |
| `tools/Dockerfile.avatar-build` | Builder-Image mit mediapipe/OpenCV; bewusst getrennt vom Laufzeit-Image |
| `tools/avatar-bundle-init.sh` | Referenzfassung des Startpfads, der `AVATAR_BUNDLE_URL` auswertet |
| `docs/AVATAR.md` | Verfahren, Begründungen und Fallstricke im Detail |

Der Generator braucht mediapipe und OpenCV und läuft deshalb im Builder-Image, nicht
im Laufzeit-Container:

```sh
docker build -f tools/Dockerfile.avatar-build -t avatar-build .
docker run --rm -v "$PWD":/out avatar-build --photo /photo/vorlage.jpg --name mia --out /out
```

Danach wird der fertige Satz hier committed; der Pages-Workflow validiert ihn und
veröffentlicht das Bundle. Im Betrieb liegt der Renderer weiterhin unter
`/home/node/.openclaw/avatar/avatar_engine.py` — ausgeliefert über die ConfigMap
`openclaw-scripts`, deren Inhalt aus `tools/avatar_engine.py` stammt.

Vor einer Änderung alle 252 Kombinationen aus 4 Lid-Zuständen, 7 Emotionen und 9
Visemen rendern und ein Testvideo erzeugen. Das Telegram-Profilbild und seine
Kreisvorschau sind zwingender Teil jeder Satz-Änderung.

## Datenschutz

Die Avatare sind Zeichnungen, keine Personen. Quellporträts gehören nicht in dieses
Repository. Nur die fertigen, für die Animation benötigten Ebenen werden versioniert.
