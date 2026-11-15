# Optional sampled history — v0.6.2b3

Beta feature for [issue #51](https://github.com/Phil-0805/hoymiles-home-assistant/issues/51).

## English

In the integration's **Configure** options, choose **History sampling**: Off
(default), 10, 15, 30 or 60 seconds. Home, Installer and Enduser profiles have the
same option. Start with 30 seconds.

This adds nine separate sensors with `(history)` in their names: PV, household,
grid and battery power, battery charge/discharge power, and the three daily
household/battery charge/battery discharge energy counters. Actual availability
still depends on the installation. Existing live sensors keep their identities,
values and update behavior. Cloud polling does not change.

**Adding history sensors alone does not reduce Recorder writes.** Exclude the
desired live originals from your existing Recorder configuration, and use their
history copies in historical charts. Current-value cards and automations can
keep using the live originals. For example, with fictitious entity IDs:

```yaml
recorder:
  exclude:
    entities:
      - sensor.my_station_pv_power
      - sensor.my_station_load_power
      - sensor.my_station_load_energy_today
```

Replace these IDs with your originals. Merge the entries into your existing
`recorder:` block, preserving other filters and settings; restart Home Assistant
after changing YAML. Confirm that any existing include filters allow the new
history entities. Do not disable the originals in the entity registry.

The excluded originals stop accumulating new Recorder history/statistics. Existing
data is neither deleted nor transferred. History copies start separate series;
the integration does not change Energy dashboard sources. Validate daily totals
before changing an existing energy setup.

Ordinary publications have at least the chosen interval between them, on the
next available source update. A 10-second interval with three-second cloud
updates may therefore publish every 12 seconds. Values are snapshots, not
averages; brief power peaks may be absent from historical graphs. Identical
values do not force new rows. Missing data becomes unavailable immediately,
and recovery is also immediate.

Daily energy still uses the original full-rate integrator. Its history copy
samples the accumulated counter, with an explicit reset at midnight in the
configured station timezone. During the final sampling interval before midnight,
every observed energy update is published to preserve the old day's tail. A
local boundary timer publishes any pending observed value at the start of that
window even if no further source update arrives; it does not query the cloud. A
normal integration reload/shutdown also flushes the latest observed same-day
counter before unloading. These and availability transitions can add rows beyond
the ordinary interval estimate. Nothing extrapolates energy across missing data.
A saved same-day guard prevents a lower restored counter from being published
as negative consumption; the copy can remain unavailable until it catches up.
An abrupt crash cannot guarantee preservation of the latest unsaved counter.

Changing the interval retains history identities. Off unloads the copies without
deleting registry entries or stored data; enabling them again reuses the identities.
While Off, remove any Recorder exclusions if you want the originals recorded again.

For optional short retention, Home Assistant provides a separate
[`recorder.purge_entities`](https://www.home-assistant.io/integrations/recorder/#action-purge_entities)
action. For example, a daily user-owned automation can retain roughly two to three
days of detailed history for one explicitly selected sensor:

```yaml
automation:
  - alias: Trim selected daily consumption history
    triggers:
      - trigger: time
        at: "04:30:00"
    actions:
      - action: recorder.purge_entities
        data:
          entity_id: sensor.my_station_load_energy_today_history
          keep_days: 2
```

This deletes matching old detailed history; it does not reduce incoming writes
or migrate/create statistics. Check statistics first. It does not target compiled
statistics, and cannot extend global Recorder retention. Merge the example into
your automation setup with the actual entity ID. The integration never configures
or runs this deletion automatically.

For a beta check, compare equivalent 24-hour row counts after Recorder exclusions
are active, including midnight and a reload. Compare original and history daily
energy totals and verify that live cards still react normally. Counts do not
measure database bytes or physical disk writes.

## Deutsch

Unter **Konfigurieren → Historien-Abtastung** sind Aus (Standard), 10, 15, 30 und
60 Sekunden wählbar. Empfehlung für den ersten Test: 30 Sekunden. Die Option
gilt auch für Installer und Enduser.

Es entstehen neun zusätzliche Sensoren mit `(Historie)` im Namen: PV-, Haus-,
Netz- und Batterieleistung, Lade-/Entladeleistung sowie die drei Tageszähler
für Hausverbrauch und Batterie-Ladung/-Entladung. Welche Werte verfügbar sind,
hängt weiter von der Anlage ab. Die vorhandenen Live-Sensoren und Cloud-Abfragen
bleiben unverändert.

**Für weniger Datenbankeinträge müssen die gewünschten Live-Originale zusätzlich
im Recorder ausgeschlossen werden.** Das YAML-Beispiel oben zeigt das Prinzip;
verwende deine tatsächlichen Original-Entitäts-IDs und ergänze deinen vorhandenen
`recorder:`-Block. Vorhandene Filter erhalten und Home Assistant anschließend
neu starten. Eventuelle Include-Filter müssen die Historien-Sensoren zulassen.
Die Originale bleiben für Live-Karten und Automationen aktiv. Historische Diagramme
verwenden die Kopien. Entitäten nicht deaktivieren.

Beide Varianten gleichzeitig aufzuzeichnen erzeugt zusätzliche Einträge. Für
ausgeschlossene Originale entstehen keine neuen Recorder-Verläufe/-Statistiken.
Alte Daten werden weder gelöscht noch übernommen. Die Kopien beginnen eigene
Zeitreihen; vorhandene Energie-Dashboard-Quellen werden nicht automatisch ersetzt.

Das Intervall begrenzt normale Veröffentlichungen; es erzwingt keine zusätzlichen
Messungen. Historienwerte sind Momentaufnahmen, kurze Leistungsspitzen können
fehlen. Ausfall und Wiederkehr werden sofort gemeldet. Die Energie-Berechnung
verwendet weiter alle Live-Messungen. Im letzten Abtastintervall vor Mitternacht
werden alle beobachteten Tageszählerwerte veröffentlicht, damit kein beobachteter
Tagesrest durch die Abtastung verloren geht. Ein lokaler Timer veröffentlicht
zu Beginn dieses Fensters einen noch ausstehenden beobachteten Stand auch ohne
weiteres Cloud-Update; er ruft keine neuen Daten ab. Beim regulären Reload/Herunterfahren
wird der letzte beobachtete Wert desselben Tages ebenfalls noch veröffentlicht.
Bei einem abrupten Absturz ist der neueste ungesicherte Stand nicht garantiert.
Ein Schutz gegen rückläufige Zähler kann die Kopie nach Neustart vorübergehend
unverfügbar halten, bis der Tageszähler wieder aufgeholt hat.

Intervallwechsel erhalten die Identität. Aus entfernt die Kopien aus dem laufenden
Betrieb, löscht aber keine Registry-Einträge oder gespeicherten Verläufe. Wenn du
danach die Originale wieder aufzeichnen möchtest, ihre Recorder-Ausschlüsse entfernen.

Die optionale Automation oben löscht ältere Detailverläufe nur für den angegebenen
Sensor mit `keep_days: 2`. Sie senkt nicht die Anzahl neuer Schreibvorgänge und
wird von der Integration weder angelegt noch ausgeführt. Statistik vorher prüfen;
kompilierte Statistik wird damit nicht gezielt gelöscht. Bei täglichem Lauf bleiben
ungefähr zwei bis drei Tage Details erhalten; globale Aufbewahrung kann kürzer sein.

Im Betatest bitte vergleichbare 24-Stunden-Zeiträume prüfen: Einträge nach aktivem
Recorder-Ausschluss, weiterhin schnelle Live-Karten, Tageswechsel, Reload und
Tagesenergie beider Varianten. Dafür reichen aggregierte Ergebnisse; keine
Datenbank, Zugangsdaten oder privaten Gerätekennungen veröffentlichen.
