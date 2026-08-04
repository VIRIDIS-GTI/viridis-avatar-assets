# Avatar-Rig aus einem Personenfoto

`make avatar` macht aus einem Foto einen Satz PNG-Ebenen samt `manifest.json`: ein
Comic-Porträt, neun Mundformen, drei Lidzustände, sieben Brauenstellungen. Damit lässt
sich ein sprechender Avatar zusammensetzen, ohne dass der Renderer je ein Foto oder ein
Bildmodell zu sehen bekommt.

```bash
export AVATAR_IMAGE_BASE_URL=https://mein-proxy/v1
export AVATAR_IMAGE_API_KEY=…
make avatar PHOTO=~/hani.jpg NAME=hani
```

Ergebnis: `assets/avatar/hani/` — rund 21 PNG, `manifest.json` und eine README, die
erklärt, wie man einzelne Ebenen austauscht.

## Wann das läuft, und wo

**Einmal je Avatar, von Hand.** Nicht in der CI, nicht beim Deployment, nicht pro
Nachricht. Das Werkzeug dafür ist ein **eigenes Image**, `Dockerfile.avatar-build`:
mediapipe und OpenCV wiegen zusammen über ein Gigabyte, werden aber nur beim
Aufbereiten gebraucht. Ein Laufzeit-Container, der sie mitschleppt, zahlt bei jedem
Neustart dafür.

**Das Foto erreicht den Laufzeit-Container nie.** Es geht in den Builder, dort bleibt
es. Weiter gereicht wird nur der fertige Ordner.

## Die vier Schritte

| | Was passiert | Deterministisch? |
|---|---|---|
| 1. Aufbereiten | Landmarks, waagerecht drehen, Drehreste wegschneiden, auf den Kreis einrahmen | ja |
| 2. Stilisieren | Bildmodell macht ein Comic-Porträt daraus | nein — würfelt bei jedem Lauf |
| 3. Einrahmen | das Ergebnis noch einmal auf den Kreis rechnen | ja |
| 4. Rig | Mund-, Augen- und Brauenebenen ausschneiden | Augen/Brauen ja, Mund je nach Modus |

### Warum zweimal eingerahmt wird

Der naheliegende Weg — Foto einrahmen, dann stilisieren — funktioniert nicht.
**Das Bildmodell komponiert den Ausschnitt neu, ganz gleich wie die Eingabe aussieht.**
Nachgemessen: eine Eingabe mit 635 px Kopfhöhe kam mit einem Kopf zurück, der 111 %
des Kreisradius füllte. Anweisungen im Prompt („keep the framing exactly as it is")
ändern daran nichts — die Edits-API bearbeitet, sie komponiert nicht.

Deshalb wird nach dem Stilisieren noch einmal eingerahmt. Da die Vorlage schon
waagerecht war, muss dabei nicht mehr gedreht werden, und es entstehen keine schiefen
Kanten.

### Warum der Kreis die Einrahmung bestimmt

Telegram zeigt Videonachrichten **rund**. Vom quadratischen Bild bleibt der
einbeschriebene Kreis übrig — die Ecken fallen weg, das sind 21 % der Fläche. Ein
Kopf, der das Quadrat gut ausfüllt, verliert im Kreis Scheitel und Kinn.

Die Kopfhöhe ist deshalb hergeleitet, nicht geraten:

> Ein Kopf ist etwa 0,75-mal so breit wie hoch, seine halbe Diagonale also `0,625·h`.
> Die muss in den Kreis passen, abzüglich der Reserve für Kopfbewegung:
> `0,625·h ≤ r·(1−0,08)` mit `r = Kante/2` ⟹ `h ≤ 0,69·Kante`. Mit Sicherheitsabstand
> **0,62**.

Das füllt rund drei Viertel des Kreisradius. Das Skript misst am Ende nach und schreibt
es ins Protokoll:

```
Kopf fuellt 77 % des Kreisradius
```

Über 95 % kommt eine Warnung — dann schneidet Kopfbewegung an.

## Die Mundformen

Neun Viseme nach Preston-Blair, genau die, die Rhubarb ausgibt: `X` (Ruhe), `A`–`H`.

Es gibt zwei Wege, und der Unterschied ist deutlich sichtbar:

**`--mouth-mode generative`** (Vorgabe). Die Bild-API bekommt eine **Maske** und malt
nur den Mundbereich neu. Alles außerhalb bleibt Pixel für Pixel unverändert — die
Identitätsdrift, die eine vollständige Neuerzeugung je Viseme hätte, ist damit
konstruktionsbedingt ausgeschlossen, nicht bloß unwahrscheinlich. Die offenen Formen
bekommen echte Zähne und ein echtes Mundinneres. Kostet acht API-Aufrufe.

**`--mouth-mode warp`**. Der Ruhemund wird gestaucht und gedehnt. Kostenlos,
deterministisch, funktioniert ohne Modellzugang — aber ein gestauchter geschlossener
Mund bleibt ein geschlossener Mund. Für `C` und `D` (weit offen) sieht das falsch aus,
weil Zähne und Mundinneres fehlen. Gut genug, um die Pipeline zu prüfen.

Augen und Brauen entstehen **immer** geometrisch, nie generativ: ein geschlossenes Auge
ist eine einfache Form, und ein Modell würde hier nur Flackern zwischen den Frames
beitragen.

## Ein Avatar ersetzen oder ändern

**Ganz neu:** `make avatar PHOTO=… NAME=…` mit neuem Namen, dann im Deployment den
Namen umstellen.

**Einzelne Ebene:** Datei gleichen Namens und gleicher Größe überschreiben. Der
Renderer liest ausschließlich `manifest.json`; wer eine Ebene woanders haben will,
ändert dort den `offset` — nicht das Bild. Die weichen Ränder der Ebenen sind Absicht,
eine harte Kante zeichnet beim Zusammensetzen eine sichtbare Naht.

**Porträt behalten, Rig neu:** Das erzeugte Comic-Porträt liegt als `portrait.png` im
Ordner. Weil das Bildmodell bei jedem Lauf etwas anderes liefert, ist das der
Anker — gefällt dir eines, bau darauf auf:

```bash
docker run --rm -v $PWD:/w openclaw-base-avatar-build \
  --from-portrait /w/portrait.png --name hani --out /w/out
```

## Ausliefern

```bash
make avatar-push NAME=hani TAG=v1     # -> ghcr.io/viridis-gti/avatar-assets:hani-v1
```

Ein `FROM scratch`-Image mit nichts als den Ebenen, ein paar MB groß. Im Betrieb holt
es ein initContainer und legt es in ein `emptyDir`:

```yaml
initContainers:
  - name: avatar-assets
    image: ghcr.io/viridis-gti/avatar-assets:hani-v1   # ← die Fassung steht hier
    command: ["sh", "-c", "cp -a /assets/. /out/"]
    volumeMounts: [{ name: avatar, mountPath: /out }]
volumes:
  - name: avatar
    emptyDir: {}
```

**Warum kein PVC und keine Bilder im Git:** Ebenen sind Bau-Ergebnisse, keine
Zustandsdaten. Ein PVC bindet an einen Knoten, braucht einen Copy-Job und — der
eigentliche Punkt — verknüpft nichts: beim Rollback bleibt es, wie es ist, und man
sieht dem Manifest nie an, welcher Avatar läuft. Git wiederum kann Binärdateien nicht
deltaen; jede Neuerzeugung legt eine vollständige zweite Kopie in die Historie, für
immer. Ein Tag im Manifest löst beides.

## Grenzen

- **Ein frontales Foto ist besser als ein schönes.** Gedrehte Köpfe, angeschnittene
  Stirn, zweite Personen im Bild — das Skript kommt damit zurecht (es dreht gerade,
  schneidet zu, nimmt das größte Gesicht), aber jeder dieser Schritte kostet Qualität.
- **Der Stil ist nicht steuerbar, nur beeinflussbar.** Das Modell liefert bei jedem
  Lauf etwas anderes. Wenn ein Ergebnis passt, halte es über `portrait.png` fest.
- **Ohne Modellzugang** greift ein OpenCV-Filter. Das ist kein Comic, das ist ein
  Filter, und das Skript sagt es auch. Für einen Funktionstest reicht es, für den
  Betrieb nicht.
- Ohne Einwilligung der abgebildeten Person gehört kein Gesicht in einen sprechenden
  Avatar.
