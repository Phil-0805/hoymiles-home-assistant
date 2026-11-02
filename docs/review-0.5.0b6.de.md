# Gesamtprüfung vor v0.5.0b6 – 29. Oktober 2026

## Ausgangspunkt und Durchführung

Geprüfter Ausgangsstand: `5ffee127028530c03a3634a41f59a98f12d7e87b`, Tag v0.5.0b5, Branch `beta/battery-settings-fallback`. GitHub hatte beim Start nur diesen Branch und `main`; `main`/Stable v0.4.2 lag auf `806021fd45823bfbd59e72c7ddcf43f90a219c60`. PR #10 war offen, Draft, nicht zusammengeführt. Issue #9 war das einzige offene Issue; #2 und #6 waren geschlossen. Die letzten Tests-, Validate- und Release-Läufe für b5 waren erfolgreich, darunter Release-Lauf `40885693579`.

Der zugewiesene lokale Projektordner war leer. Prüfung und Korrekturen wurden in einem separaten Klon auf `review/0.5.0b6` erstellt; es gab keine lokalen Nutzeränderungen zu überschreiben. Keine authentifizierten Hoymiles-Abfragen, Steuerbefehle oder Hardwaretests wurden ausgeführt. Es wurden ausschließlich öffentliche Quellen und synthetische Testdaten verwendet.

Gesichtet wurden alle Python-Module der Integration, Plattformen, Konfigurations-/Optionsfluss, Transport-/Authentifizierungswege, Hintergrundaufgaben, Speicherung, Registermigration, Diagnosen, Decoder, Tests, Übersetzungen, beide READMEs, HACS-Metadaten und die drei CI-Workflows. Die Prüfung begründet keine Garantie der Fehlerfreiheit oder unabhängige Sicherheitszertifizierung.

## Bestätigte Probleme und Korrekturen

| Priorität | Fehler in b5 / Auswirkung | Korrektur in b6 |
| --- | --- | --- |
| Hoch | Reserve-SOC verwendete trotz „fresh snapshot“-Beschreibung den bis zu 30 Minuten alten Cache. Eine geänderte obere SOC-Grenze oder inzwischen aktives TOU konnten überschrieben werden. | Auch vor Reserve-SOC frische Einstellungen unter dem Schreiblock lesen, Voraussetzungen erneut prüfen, kompletten aktuellen Zielblock verwenden und zurücklesen. |
| Hoch | JSON wurde ohne Größen-/Verschachtelungsgrenze gelesen; tiefe Strukturen erreichen rekursive Verbraucher. | Maximal 8 MiB dekomprimierter HTTP-Body, maximal 32 Container-Ebenen, kontrollierte JSON-Fehler. Challenge-/Token-Formen vor Verwendung prüfen. |
| Hoch | Beliebige Backend-Fehlertexte konnten in Logs, HA-Fehlern und Einstellungsattributen erscheinen. Auch eine bereinigte äußere Fehlermeldung konnte über die verkettete Transportausnahme eine signierte URL offenlegen. | Feste Fehlermeldungen und unterdrückte sensitive Transportketten; bekannte Fallback-Erkennung „device list is empty“ bleibt mit festem Text erhalten. Kein Nachweis eines tatsächlich veröffentlichten Tokens. |
| Mittel | Für `ConfigEntryAuthFailed` fehlte ein Reauth-Schritt. Nach Passwortänderung fehlte die vorgesehene Wiederanmeldung am bestehenden Eintrag. | Passwortdialog für dasselbe Konto; Anmeldung und Zugriff auf dieselbe Station prüfen, Passwort am bestehenden Eintrag aktualisieren. Optionen/Identitäten bleiben erhalten. |
| Mittel | Ein fehlgeschlagener Live-Abruf unterbrach die Energietrapeze nicht, sofern der nächste Erfolg innerhalb einer Minute kam. | Integrationsanker bei Cloud-/Auth-/Rate-Limit-Fehlern zurücksetzen; keine Energie über diesen Ausfall schätzen. |
| Mittel | Anzeige wandelte gebrochene `brs`-Werte mit `int()` in bekannte Richtungen um, während Energie/Status sie als unbekannt behandelten. | Nur exakte 0/1/2 verwenden; unbekannte Codes behalten den bestehenden Vorzeichen-Fallback. Keine neue Statuszuordnung erfunden. |
| Mittel | Beschädigte Gzip-Nutzdaten konnten `zlib.error` statt des behandelten Verbindungsfehlers auslösen. | Auch diesen Dekompressionsfehler kontrolliert abfangen. |
| Mittel | Fehler bei Stationssummen ließen den Erfolgszeitpunkt unverändert; dadurch wurde im Live-Takt statt minütlich erneut angefragt. | Letzten Versuch getrennt vom letzten Erfolg verfolgen; auch Fehler höchstens im Minutentakt erneut abfragen. |
| Mittel | Erfolgreiche Live-Abfragen konnten beliebig alte Stationssummen weiter sichtbar halten; beim lokalen Tageswechsel blieb der Vortageswert als „heute“ verfügbar. | Summen nach zwei Minuten ohne erfolgreiche Antwort unverfügbar; Tages-/Monats-/Jahresgrenzen separat prüfen. Keine gespeicherten Werte oder Statistikidentitäten löschen. |
| Mittel | `Retry-After` wurde auf einen Tag gekürzt; längere Herstellerpausen konnten vorzeitig neue HTTP-Starts erlauben. | Volle Pause im Account-Runtime erhalten; nur HA-Wiederaufwachtermine auf einen Tag begrenzen und dann die noch laufende Pause erneut prüfen. |
| Mittel | Gemeinsamer Login-Lock verhinderte nach einem Transportfehler keine weiteren Loginversuche anderer Anlagen. | Gemeinsame 60-Sekunden-Pause bei automatischen Login-Transportfehlern; bestehende längere Rate-Limit-Pausen bleiben erhalten. |
| Mittel | Falsche innere Antworttypen bei Live-URI/Stationssummen führten zu `AttributeError` bzw. späteren Sensorfehlern. | Antwortformen prüfen und als Verbindungsfehler behandeln. |

Keine automatischen Wiederholungen von Schreibbefehlen wurden eingeführt. Die reguläre Abfragefrequenz wurde nicht erhöht. Bestehende Entity-/Unique-IDs, Gerätezuteilung, Speicherformat, Zustandseinheiten und Statistikklassen bleiben erhalten. Die b5-Temperaturmigration bleibt unverändert und wird weiterhin einschließlich benutzerdefinierter Namen, deaktivierter und fremder Entitäten sowie abhängiger Geräte getestet.

## Tatsächlicher HTTP-Bedarf

Jeder Aufruf von `_json` bzw. `_async_binary_data` ist **eine** HTTP-Anfrage. Asynchrone Aufträge zählen zusätzlich zu jedem einzelnen Statuspoll. Die folgenden Zahlen sind aus Kontrollfluss und Konstanten abgeleitet, keine Messung gegen ein reales Konto und kein bestätigtes Herstellerlimit.

| Vorgang | Anzahl / Rhythmus |
| --- | --- |
| Anmeldung | 2 POSTs: Pre-Inspection und Login. Token lokal 90 Minuten gültig; gemeinsame Erneuerung für eingerichtete Einträge mit identischen Zugangsdaten. |
| Einrichtungsdialog | Zusätzlich eigene kurzlebige Client-Anmeldung, 1–20 Listenseiten und 1 Gerätebaumprüfung. Der Dialog teilt den Runtime-Pool eingerichteter Einträge derzeit nicht. Die spätere Einrichtung kann erneut anmelden. |
| Normaler Live-Zyklus | 1 POST; bei fehlender URI zuvor 1 URI-POST. Intervall mindestens 3 Sekunden bzw. längere `dly`, zusätzlich Laufzeiten. |
| Live-Wiederherstellung | Höchstens 2 Versuche, bei kaltem URI-Cache bis zu 4 POSTs insgesamt; eine erforderliche Anmeldung kostet zusätzlich 2 POSTs, ggf. auch die Anmeldung vor dem ersten Versuch. Kein unmittelbarer Retry bei Rate-Limit. |
| Stationssummen | 1 POST je Minute und Station, ab b6 auch im Fehlerfall. |
| Normale Modulwerte | 1 POST **pro PV-Eingang** alle 5 Minuten. Bekannter HMS-Eingangszahl folgen; unbekanntes Modell weiterhin 4 Eingänge. Kein Bulk-Aufruf behauptet. |
| Zusätzliche Wechselrichterwerte | Opt-in, 1 zusätzlicher Stations-POST je 5-Minuten-Durchlauf. |
| Batterietemperaturen | Opt-in, 1 zusätzlicher Stations-POST je 5-Minuten-Zyklus, auch bei mehreren Packs. |
| Erfolgreiche Aktion-83-Einstellungslesung | 1 Read-Auftrag + P Statuspolls, P = 1 bis 10. Regulär etwa alle 30 Minuten; manuell frühestens 30 Sekunden nach einer abgeschlossenen/angesetzten Aktualisierung, laufende manuelle Lesungen werden zusammengefasst. |
| Einstellungs-Fallback | Fehlgeschlagener Aktion-83-Pfad **plus** Aktion 1013: jeweils Auftrag + gegebenenfalls bis zu 10 Polls; nach einem parsebaren 1013-Ergebnis weitere 5 Benutzer-Einstellungsproben. Bei leerer Geräteliste zusätzlich 1 Gerätebaumabfrage und je gefundenem Typ-12-Ziel weitere 1013-Aufträge/Polls bis Erfolg/Abbruch. Die Zahl D der Ziele hat keine eigene kleine Obergrenze, ist aber durch Antwortlimit und 120-Sekunden-Timeout der Hintergrundlesung begrenzt. Auth-/Rate-Limits sind eigene Fehlerpfade; gemeinsame Budgetpausen unterbinden weitere HTTP-Starts. |
| Modellermittlung bei Einrichtung | 1 Gerätebaum; falls nötig 1 Web-Baum und bis zu 20 Detailproben innerhalb eines gemeinsamen 12-Sekunden-Zeitbudgets. |
| Expliziter Schreibvorgang | Ab b6 sowohl Modus als auch SOC: 1 frische Einstellungslesung vorab, 1 Schreibauftrag (Aktion 83 mit Statuspolling; alter `battery_config`-Pfad ohne separaten Schreibpoll), danach bis zu 8 vollständige Einstellungslesungen mit 3 Sekunden Abstand bei Nichtübereinstimmung. Kein erneutes Senden des Schreibauftrags. |

Auf dem durchgehend erfolgreichen Aktion-83-Pfad mit je einem Statuspoll bedeutet ein bestätigter Schreibvorgang typischerweise **6 HTTP-Anfragen**: 2 vorab, 2 für Auftrag/Status, 2 zur Rücklesebestätigung. Mit 10 Polls pro Vorgang und allen 8 Rückleseversuchen sind es **110**, ohne zusätzliche Anmeldung; ein Fehler kann früher abbrechen. Fallback-Lesungen können den Bedarf deutlich weiter erhöhen. Deshalb sind kurze Pollintervalle nicht mit einer vollständigen Transaktion gleichzusetzen.

Rechenbeispiel je Station/Tag bei idealisierten Sollintervallen: 3-Sekunden-Live bis etwa 28.800; Summen etwa 1.440; vier PV-Eingänge etwa 1.152; 48 erfolgreiche Einstellungslesungen mit einem Statuspoll etwa 96. Zusammen etwa **31.488**, zuzüglich Kontoanmeldungen (bei 90 Minuten etwa 32 POSTs/Tag), Einrichtung, Wiederherstellung und Bedienung. Beide optionalen Messwertpfade zusammen etwa 576 weitere POSTs/Tag. Laufzeiten und HA-Terminierung reduzieren/verschieben diese Zahlen; es ist keine gemessene Tagesquote.

Mehrere Stationen addieren ihre Stationslast. Sie teilen bei identischen Zugangsdaten den Token, Login-Lock, mindestens 1 Sekunde zwischen HTTP-Starts, maximal 2 laufende HTTP-Anfragen und HTTP-429-Pausen. Andere Apps, abweichende Passwörter und der Einrichtungsdialog gehören nicht zu diesem Pool. Es gibt keine zusätzliche feste Tagesquote. HTTP `Retry-After` wird als Sekunden oder Datum interpretiert, mit mindestens 60 Sekunden Pause. Ab b6 bleibt auch eine mehrtägige Pause vollständig im Account-Budget erhalten. Nur der HA-Wiederaufwachtermin ist auf 86.400 Sekunden begrenzt; ein früheres Aufwachen erlaubt keine vorzeitigen HTTP-Starts. Dies ist kein bestätigtes Herstellerlimit.

## Protokoll- und Sicherheitsbelege

- Hersteller-[WorkModeDrawer](https://static.hoymiles.com/cdncache/website/js/index-COaHho1l.js) erneut öffentlich geladen: SHA-256 `d932523a3183d7d24ad0ea26ae544eeaf63075b50189f3b5368974a9d0efd8f4`. SOC-Felder und gespeicherte TOU-Auswahl stimmen mit [dem Aktion-83-Beleg](work-mode-83.md) überein. Aktion-83-Modi 2/3 werden weiterhin ausdrücklich von den Aktion-1013-Kennungen unterschieden.
- Hersteller-[API-Bundle](https://static.hoymiles.com/cdncache/website/js/index-CTUY73vV.js) erneut geladen: SHA-256 `a2790e4875668e9de1f8a3aacb0164bffbfe8cfb6ca4180e042330aac3240c98`. Dedizierter `au_inv/au_s_c`-Temperaturendpunkt und `station/setting/battery_config` stimmen mit den dokumentierten Pfaden überein. Temperaturbeleg: [separates Dokument](battery-temperature-api.md).
- [Offizielle Hoymiles-FAQ](https://www.hoymiles.com/de/faq.html) verweist für MS-A2 auf MQTT-Dokumentation. Das belegt keine Zuordnung numerischer Consumer-Cloud-EMS-/Ladecodes. Es wurden keine MQTT-/lokalen Moduskennungen in die Cloudsteuerung übernommen.
- Der per Commit und SHA-256 festgelegte öffentliche [Node-RED-Decoder](https://github.com/pinguin45orga/node-red-contrib-hoymiles-home/blob/e48ac860e2d1d17fdad108be4dfe306e511608e2/nodes/hoymiles-modules/module-data.js) stimmt erneut mit der synthetischen Protobuf-Datei überein. Das ist Formatprüfung, kein Hardwarebeleg.
- HTTPS-Zielprüfung, Zertifikats-/Hostnamenprüfung, Redirect-Sperre, begrenzte Binärantworten und Diagnose-Allowlist bleiben aktiv. Keine Zugangsdaten wurden beschafft oder in Testdateien kopiert. Alle neuen Geheimnis-Testmarker sind synthetisch.
- Keine neue Android-App-/APK-Analyse durchgeführt. Historische Berichte über einen blockierten APK-Download werden nicht als Analyse dargestellt. Kein umfassender Schwachstellen-Scan sämtlicher Home-Assistant-Drittbibliotheken durchgeführt.

## Prüfung und Beweisgrenzen

Unveränderter b5-Ausgangspunkt: **34 Unit-Tests + 223 HA-Tests erfolgreich**. Neue gezielte Fälle wurden jeweils vor der entsprechenden Korrektur ausgeführt: **17 fehlgeschlagene Fälle** über SOC-Snapshot, JSON-Limits, Fehlertext/Traceback, Relaiscode, Energieausfall, Reauth, Deflate, Stationssummen, Login-Pause und innere Antwortformen. Ein zusätzlicher gebrochener Relaiscode war bereits korrekt; er wird nicht als weiterer behobener Fehler gezählt.

Endstand: **34 Unit-Tests + 247 HA-Tests**. Zusätzliche Positiv-/Negativprüfungen betreffen gültige JSON-Nullwerte, gescheiterte Wiederanmeldung ohne Passwortmutation, Monats-/Jahreswechsel und unveränderte gespeicherte Energie. Bestehende Rücklese-Negativtests erhalten einen getrennten Vorab-Snapshot und prüfen unverändert, dass falsche Rücklesung fehlschlägt und genau ein Schreibauftrag gesendet wird. Keine Prüfansprüche wurden entfernt.

Ausführbare Prüfungen:

```text
python -m unittest discover -s tests -v
python -m pytest tests/ha -q
python -m compileall -q custom_components tests scripts
git diff --check
python scripts/compare_nodered_reference.py --reference-file <checksum-matching-public-file>
python scripts/check_release_readiness.py --version 0.5.0
```

Die letzte Prüfung muss bei den offenen Nachweisen mit Fehler abbrechen. Übersetzungsschlüssel DE/EN/strings, Manifest-/Kandidatenversion und lokale Markdown-Verweise werden zusätzlich verglichen. HACS/Hassfest werden über CI geprüft; die Beta-Publikation bleibt von erfolgreichen Validate-/Test-Jobs abhängig. Die veröffentlichten CI-Läufe sind der maßgebliche Nachweis für diese externen Prüfungen.

## Offene Punkte und Stable-Voraussetzungen

**Gerätebelege fehlen:** Betroffener 4020-X-Nutzer muss Einstellungen/Fallback, PV-Quelle bei zeitgleichem App-Vergleich, Batterierichtung und verfügbare Leistungsfelder prüfen. HMS-1000-2WB-Modellbestätigung, Nacht-/Tagerholung, Neustart/Optionsänderung/Verlauf sowie reale Genauigkeit optionaler Werte bleiben offen. Moduswechsel und Batterietemperatur funktionieren laut Maintainer auf seinem System; diese Rückmeldung wird nicht auf andere Modelle oder b6 übertragen.

**Messzeitpunkte:** Zusätzliche Wechselrichterwerte bewahren eigene Hersteller-Zeitpunkte und altern pro Messwert. Normale PV-Eingangsdiagramme verwenden noch Antwortalter. Ein ständig wiederholter alter Punkt wird deshalb nicht sicher erkannt. Batterietemperaturen haben laut bekanntem Endpunkt keinen Messzeitstempel; `fetched_at` ist ausdrücklich nur Cloud-Empfangszeit. Auch Live-Daten ohne verlässlichen Herstellerzeitstempel können nur nach Abruf/Verbindungsstatus bewertet werden. Ein Softwaretest kann das physische Messalter nicht beweisen.

Minimale zusätzliche Information für eine belastbare normale Diagramm-Zeitzuordnung: **anonymisierte Labels, Typ/Serienlänge und letzte ein bis zwei numerische Werte eines einzelnen PV-Eingangs**, dazu lokale Anlagenzeitzone und zeitgleicher App-Zeitpunkt. Ohne Kennungen, URL/Token, Kontodaten oder vollständigen Rohdump. Eine vom Nutzer bereitgestellte Offline-Datei genügt; es ist keine Live-Abfrageserie erforderlich.

**Steuerung:** Die API liefert keine atomare Versionsbedingung zwischen frischer Lesung und Schreiben. Während eines expliziten Befehls sind gleichzeitige App-Änderungen zu vermeiden; Rücklesen kann Konflikte erkennen, aber nicht rückwirkend verhindern. Die fünf alten Benutzer-Einstellungsproben und nicht separat begrenzte Zielanzahl sind weiterhin komplexe Legacy-Fallbacks. Eine Optimierung benötigt echte anonymisierte Geräteantworten, um unterstützte Geräte nicht vorschnell auszusperren.

**Weitere Verdachts-/Verbesserungspunkte:** Einrichtungsdialog außerhalb des Account-Pools, Nacht-/Wiederverbindungsverhalten und mögliche zukünftige Bulk-Abfragen verdienen eine Folgerunde. Unbenutzter Aktion-1013-Schreibhelfer und dessen nur getesteter Payload-Builder sind optionale Bereinigung; in dieser Beta kein weiterer Umbau. Unverifizierte EMS-/Ladecodes und maximale Leistung behalten Rohdarstellung bzw. fehlende Einheit/Steuerung. Eine pauschale Geräteunterstützung ist nicht bewiesen.

**Stable bleibt gesperrt:** Alle neun Nachweiszeilen in `release-readiness.json` bleiben offen, einschließlich eigener Zeilen für Moduswechsel und Batterietemperatur. Erforderlich sind echte Geräte-/App-Rückmeldungen für den Kandidaten, dokumentierte Grenzen der Messaktualität, Klärung relevanter Restfehler, grüne CI und ausdrückliche Maintainer-Freigabe. Keine automatische Zusammenführung oder Stable-Veröffentlichung.
