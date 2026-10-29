# Testplan für den größeren Release 0.5.0

Kandidat: **0.5.0b1**, ausschließlich als Vorabversion. Die Implementierung und automatisierte Tests ersetzen keine Bestätigung am betroffenen Gerät. Stable bleibt 0.4.2.

## Testen ohne Neueinrichtung

1. In HACS Vorabversionen anzeigen, 0.5.0b1 installieren und Home Assistant neu starten. Die bestehende Integration behalten.
2. Prüfen, ob Geräte, Entitäten, Verlauf und Tageszähler weiterhin vorhanden sind. Keine Geräte löschen, um Namensprobleme zu beheben.
3. Unter Konfigurieren die tatsächliche Zeitzone der Anlage prüfen. Standard ist die HA-Zeitzone. Die optionalen zusätzlichen Wechselrichter-Messwerte sind zunächst ausgeschaltet.

## Offene Nutzermeldungen bestätigen

| Punkt | Konkreter Vergleich | Noch benötigte Bestätigung |
| --- | --- | --- |
| HMS-1000-2WB | Nach Neustart bei Tageslicht Modell und normale Messwerte prüfen. | Rückmeldung des betroffenen Nutzers zu Issue #6. |
| Batterie-Absturz | Batterieeinstellungen aktualisieren; Logs auf `work_mode_error`/`UnboundLocalError` prüfen. | Betroffener 4020-X-Nutzer bestätigt, dass der Fehler ausbleibt und der Zugriffszustand plausibel ist. |
| PV-Leistung | Bei Sonne HA-Attribute `pv`/`pv2` und App zeitgleich vergleichen. Bei belegtem Unterschied die passende Quelle konfigurieren. | Gewählte Quelle und beobachtete Leistungen dokumentieren. Keine Addition ohne Nachweis. |
| Statuszahlen | Batterieaktivität bei Laden, Entladen und Leerlauf mit der App vergleichen. Rohcodes bleiben als solche bezeichnet. | Betroffener Nutzer bestätigt Anzeige/Dokumentation. Die Bedeutungen von `ems`/`chs` sind weiterhin nicht belegt. |
| Maximale Leistung | Prüfen, ob die App für dieses Gerät/den Modus einen entsprechenden Wert anbietet. Diagnose enthält nur bekannte numerische Einstellungsfelder. | Verfügbarkeit oder die dokumentierte Einschränkung bestätigen; Einheit und Steuerbarkeit nicht erfinden. |
| Betriebsmodus | Nur ein bestätigter Modus ergibt keine bedienbare Auswahl. Der gelesene Modus bleibt als Diagnose sichtbar. | Klären, ob mehrere Modi in der App tatsächlich verfügbar sind. Ohne passende Protokolldaten werden keine zusätzlichen Befehle angeboten. |
| Tag/Nacht | Nachts Verfügbarkeit, morgens automatische Erholung sowie Tageszähler/Verlauf prüfen. | Testzeitraum und Ergebnis dokumentieren. |
| Neue Messwerte | Optional aktivieren; Temperatur, Netzfrequenz und AC-Spannung mit App vergleichen. Bis zum ersten passenden Datenpunkt können sie unbekannt sein. | Reale Werte und Geräteversion dokumentieren. Die bisherige Validierung des zusätzlichen Datenformats ist synthetisch. |

Eine Bestätigung sollte Kandidatenversion, Modell, durchgeführten Test und beobachtetes Ergebnis nennen. Im passenden GitHub-Issue dokumentieren; Kontodaten, Seriennummern, Zugangstoken und private Screenshots nicht veröffentlichen. Rückmeldungen von Facebook können vom Maintainer mit Herkunft und Ergebnis im Issue festgehalten werden. Ein automatisierter Test allein ist keine Nutzerbestätigung.

## Abfragezeiten und Grenzen

- Live-Leistung: mindestens drei Sekunden bzw. die längere serverseitige Wartezeit `dly`.
- Moduldiagramme: höchstens alle fünf Minuten. Zusatzdaten bei ausdrücklicher Aktivierung ebenfalls höchstens alle fünf Minuten, eine zusätzliche Stationsabfrage je Durchlauf.
- Batterieeinstellungen: regulär alle 30 Minuten. Manuell frühestens nach 30 Sekunden; gleichzeitig laufende Anforderungen werden zusammengefasst.
- Pro identischen Zugangsdaten teilen Anlagen Token und Abfragebudget: mindestens eine Sekunde zwischen HTTP-Starts, höchstens zwei gleichzeitige HTTP-Abfragen. Das Budget gilt für diese Integration, nicht für andere Apps/Integrationen.
- HTTP 429 pausiert das gesamte gemeinsame Budget entsprechend Retry-After, mit konservativen Grenzen von einer Minute bis einem Tag. Beim täglichen Login-Limit wird die automatische Anmeldung eine Stunde zurückgestellt. Die tatsächlichen Hoymiles-Quoten sind nicht veröffentlicht; diese Maßnahmen garantieren daher keine bestimmte erlaubte Tageszahl.
- Lesevorgänge dürfen begrenzt wiederholt werden. Schreibbefehle werden nicht automatisch wiederholt.

## Node-RED-Vergleich reproduzieren

`python scripts/compare_nodered_reference.py` lädt ausschließlich den per Commit und Prüfsumme festgelegten öffentlichen Node-RED-Decoder. Mit `--reference-file /pfad/module-data.js` läuft der Vergleich vollständig offline. Node.js muss verfügbar sein.

Es wird derselbe synthetische Protobuf-Datensatz wie in den Python-Tests ausgewertet. Es werden weder Hoymiles-Konten kontaktiert noch Gerätebefehle gesendet. Das bestätigt das Datenformat, nicht die Funktionsfähigkeit an einem bestimmten Gerät.

## Freigabe des Stable-Releases

Die sieben Prüfbereiche in `release-readiness.json` sind zunächst **unbestätigt**. Bestätigungen werden nur anhand tatsächlicher Rückmeldungen eingetragen, mit getesteter Kandidatenversion, bestätigender Person und Link auf den Issue-Kommentar. Bei fachlichen Codeänderungen nach dem Test muss die betroffene Prüfung erneut erfolgen.

Der Stable-Workflow prüft diesen Nachweis und die separate Maintainer-Freigabe. Solange ein Nachweis fehlt, wird kein neuer Stable-Release veröffentlicht. Zusätzlich müssen Tests, HACS und Hassfest erfolgreich sein. Die Prüfung schützt vor versehentlicher Veröffentlichung; sie kann den Wahrheitsgehalt eines Gerätetests nicht selbst feststellen.
