# VIRIDIS Avatar Assets

Versionierte Ebenensätze für die gezeichneten Video-Avatare der VIRIDIS Green-Tech
Investment AG. Der Renderer liest ausschließlich `manifest.json`; ein Satz ist damit
vollständig austauschbar, ohne den Renderer zu ändern.

## Sätze und Versionen

| Satz | Version | Öffentlicher Bundle-Pfad nach aktiviertem Pages-Deploy |
|---|---:|---|
| `neo` | 1 | `https://VIRIDIS-GTI.github.io/viridis-avatar-assets/neo/v1/neo-v1.tar.gz` |
| `andy` | 2 | `https://VIRIDIS-GTI.github.io/viridis-avatar-assets/andy/v2/andy-v2.tar.gz` |
| `mia` | 2 | `https://VIRIDIS-GTI.github.io/viridis-avatar-assets/mia/v2/mia-v2.tar.gz` |
| `otto` | 1 | `https://VIRIDIS-GTI.github.io/viridis-avatar-assets/otto/v1/otto-v1.tar.gz` |

Die URLs sind der feste Vertragsname der GitHub-Pages-Veröffentlichung. Sie werden
erst erreichbar, wenn GitHub Pages für dieses Repository aktiviert ist. Neben jedem
Archiv veröffentlicht die Action eine Datei `<bundle>.sha256` sowie `index.json`.

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

Die GitHub Action `.github/workflows/deploy-pages.yml` führt exakt diesen Befehl bei
Push nach `main` aus, lädt das Ergebnis als Pages-Artefakt hoch und deployt es nach
GitHub Pages. Sie benötigt die Standardberechtigungen `pages: write` und `id-token:
write`; keine Registry- oder privaten Deploy-Schlüssel.

## Verwendung im Container

`openclaw-base` verwendet `AVATAR_BUNDLE_URL` beim ersten Containerstart sicher und
atomar. Dazu gehören HTTPS-Zwang, Retry/Timeout, optionaler SHA-256-Vergleich,
Archiv-Pfadprüfung und Manifest-Validierung. Beispiel:

```yaml
- name: AVATAR_ASSETS_DIR
  value: /home/node/.openclaw/avatar/mia
- name: AVATAR_BUNDLE_URL
  value: https://VIRIDIS-GTI.github.io/viridis-avatar-assets/mia/v2/mia-v2.tar.gz
- name: AVATAR_BUNDLE_SHA256
  value: <Wert aus mia-v2.tar.gz.sha256>
```

Ohne `AVATAR_BUNDLE_URL` bleibt der bestehende InitContainer-/Git-Mechanismus
unverändert. Infrastruktur-Manifeste sollen künftig nur diese drei Werte je Bot
konfigurieren, nicht mehr Repo-Klone oder avatar-spezifische InitContainer enthalten.

## Avatar erzeugen oder ändern

Die Generatorlogik stammt aus `openclaw-base` (`scripts/build_avatar.py` und
`Dockerfile.avatar-build`). Sie ist dort weiterhin das Werkzeug für den einmaligen
Aufbau aus einer Vorlage. Danach wird der fertige Satz hier committed, validiert und
als Bundle veröffentlicht. Der Renderer selbst bleibt bei
`/home/node/.openclaw/avatar/avatar_engine.py`.

Vor einer Änderung alle 252 Kombinationen aus 4 Lid-Zuständen, 7 Emotionen und 9
Visemen rendern und ein Testvideo erzeugen. Das Telegram-Profilbild und seine
Kreisvorschau sind zwingender Teil jeder Satz-Änderung.

## Datenschutz

Die Avatare sind Zeichnungen, keine Personen. Quellporträts gehören nicht in dieses
Repository. Nur die fertigen, für die Animation benötigten Ebenen werden versioniert.
