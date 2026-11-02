# Geräte prüfen und Probleme eingrenzen

## Nach einem Update

- Home Assistant neu starten und die vorhandene Integration behalten.
- Prüfen, ob Entitäten, eigene Namen, deaktivierte Entitäten und Verlauf erhalten sind.
- Unter **Konfigurieren** die tatsächliche Zeitzone der Anlage einstellen.
- Optionale Wechselrichterwerte und Batterietemperaturen bei Bedarf aktivieren. Bis zum ersten Abruf können sie unbekannt sein; diese Abfragen laufen alle fünf Minuten.

## PV und Verbrauch

Bei Tageslicht die Werte in Home Assistant zeitgleich mit der S-Miles-Home-App vergleichen. Am Sensor **PV-Leistung** stehen die Attribute `pv`, `pv2` und die verwendete Quelle.

Unter **Einstellungen → Geräte & Dienste → Hoymiles S-Miles Home → Konfigurieren** lässt sich die **Quelle der PV-Leistung** auswählen:

- **Automatisch:** `pv2`, falls verfügbar, sonst `pv`. Null ist ein gültiger Wert.
- **pv / pv2:** Nur das ausgewählte Feld; fehlt es, bleibt der Messwert unbekannt.

Eine andere Quelle nur anhand des App-Vergleichs wählen. Die Felder werden nicht addiert. Fehlende Verbrauchswerte lassen sich mit dieser PV-Option nicht korrigieren; die Cloud muss passende Lastwerte liefern.

Beim gemeldeten **4020-X-Aufbau** fehlen Verbrauchswerte und die PV-Leistung ist überwiegend null. Ursache, Wechselrichtermodell und Ergebnis des Quellenwechsels sind noch offen: [Issue #9](https://github.com/Phil-0805/hoymiles-home-assistant/issues/9).

## Batterie und weitere Messwerte

- **Batterieeinstellungen aktualisieren** liest Einstellungen erneut und sendet keinen Steuerbefehl. Zwischen manuellen Aktualisierungen mindestens 30 Sekunden warten.
- Modus oder Reserve-SOC nur bewusst ändern, ohne gleichzeitig in der App zu bearbeiten. Anschließend Modus, SOC-Grenzen und gespeicherten Zeitplan in der App kontrollieren. Bei einem unklaren Ergebnis zuerst dort den tatsächlichen Zustand prüfen.
- Temperaturen und Batterierichtung mit der App vergleichen. Fehlende Messwerte sind nicht gleich null. Unbekannte Rohcodes werden nicht als bestätigte Betriebszustände interpretiert.
- Nach einem Netz-/Cloud-Ausfall prüfen, ob die Werte selbstständig wiederkehren. Berechnete Energie kann während des Ausfalls Lücken haben.

Batterietemperaturen und normale PV-Eingangsdiagramme verwenden das Alter der Cloud-Antwort; wiederholt gelieferte alte Messungen lassen sich damit nicht sicher erkennen. Zusätzliche Wechselrichterwerte behalten ihren eigenen Hersteller-Messzeitpunkt.

## Ein Problem melden

Integrationsversion, Home-Assistant-Version, Geräte-/Wechselrichtermodell und eine kurze Fehlerbeschreibung angeben. Bei Messwertabweichungen den Zeitpunkt, die Anlagenzeitzone und den zeitgleichen App-Vergleich ergänzen. Die Integrationsdiagnose kann ebenfalls helfen.

Keine Passwörter, Tokens, signierten URLs, Seriennummern oder ungeschwärzten privaten Screenshots veröffentlichen.
