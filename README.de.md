# Hoymiles S-Miles Home für Home Assistant

[English](README.md) | **Deutsch**

Inoffizielle Home-Assistant-Integration für **S-Miles-Home**-Konten. Sie liest
Daten direkt aus der Hoymiles-Cloud; Node-RED, MQTT und lokaler Zugriff auf den
Wechselrichter sind nicht erforderlich. Entwickelt und getestet mit einem
HMS-2000-4WB mit HiBattery. Im Betatest für 0.4.2 am 28. Oktober 2026 bestätigte
der Maintainer die korrekten Modellanzeigen und PV-Messwerte an Anlagen mit
HMS-2000-4WB und HMS-800-2WB. Damit sind nicht sämtliche Funktionen oder alle
Firmware- und Kontokombinationen bestätigt.

Für eine **HiBattery 4020-X mit einem Zusatzspeicher** bestätigt ein Nutzer
passende PV-Werte nach Auswahl der Quelle, Batterietemperaturen, Relaisrichtung
und funktionierende Batteriebefehle unter v0.5.1. Diese Beobachtungen gelten für
diesen Aufbau. Die maximale Leistungseinstellung bleibt über den verwendeten
Einstellungsabruf unbekannt; einige Rohstatuscodes sind undokumentiert. Siehe
[Issue #9](https://github.com/Phil-0805/hoymiles-home-assistant/issues/9).

## Anlage beim Einrichten auswählen

Ab Version 0.4.0 zuerst mit dem S-Miles-Home-Konto anmelden und anschließend die
Anlage anhand von Name und numerischer Station-ID auswählen. Für eine weitere
Anlage die Integration erneut hinzufügen. Bereits eingerichtete Anlagen und
bestehende Kennungen bleiben erhalten.

Die Station-ID lässt sich alternativ direkt in das Auswahlfeld eingeben. Falls
keine Anlagen erkannt werden, bietet die Einrichtung eine manuelle ID-Eingabe.
Vor dem Speichern wird die ID anhand der Geräteliste des Kontos geprüft.

Anlagenauswahl und Duplikaterkennung wurden vom Maintainer am 26. Oktober 2026
mit seinem Konto getestet; vorhandener Verlauf und Messwerte blieben erhalten.
Andere Konten und Anlagenmodelle können sich bei dieser inoffiziellen API anders
verhalten. Für die manuelle Einrichtung siehe [Station-ID finden](#station-id-finden).

## Funktionen

- Aktuelle PV-, Hausverbrauchs-, Netz- und Batterieleistung, soweit von der Anlage geliefert
- Dauerhaft gespeicherter täglicher Hausverbrauch, berechnet aus der aktuellen Last
- Korrekte WB-Batterieladerichtung anhand des aktuellen Relaiszustands
- Separate positive Leistungssensoren für Laden und Entladen der Batterie
- Dauerhaft gespeicherte tägliche Energiezähler für Laden und Entladen
- Einstellbarer Reserve-SOC und Batteriemodus mit anschließender Rückleseprüfung
- Schreibgeschützte Diagnosewerte der Batterieeinstellungen
- Batterieladezustand und unverarbeitete Betriebszustände
- Leistung, Spannung und Strom je Modul aus Fünf-Minuten-Diagrammen, soweit verfügbar
- Verbindungsstatus der Anlage
- Tages-, Monats-, Jahres- und Gesamtenergie, soweit vom Stationsendpunkt geliefert
- Einrichtung über die Benutzeroberfläche von Home Assistant

## Batteriesteuerung

Batteriebefehle sind standardmäßig gesperrt, auch beim Update einer bestehenden Installation. Unter **Einstellungen → Geräte & Dienste → Hoymiles S-Miles Home → Konfigurieren** die Option **Batteriesteuerung freigeben** einschalten, um Modus und Reserve-SOC zu ändern. Ausschalten aktiviert wieder den Nur-Lese-Betrieb. Kennungen und Verlauf vorhandener Entitäten bleiben erhalten; Messwerte und Einstellungsabfragen funktionieren auch bei gesperrter Steuerung. Gleichzeitige Änderungen in der S-Miles-Home-App vermeiden.

Für die aktuellen Schutzmaßnahmen v0.5.1 oder neuer verwenden. Frühere Versionen sind überholt. Nach dem Update Home Assistant neu starten und die Batteriesteuerung bei Bedarf ausdrücklich freigeben. Das gilt auch für bestehende Automationen, die Modus oder Reserve-SOC ändern.

## Neu in Beta v0.5.2b2: obere Ladegrenze

Die Beta v0.5.2b2 ergänzt einen Sensor und einen Regler für den maximalen
Lade-SOC im unterstützten Eigenverbrauchsmodus. Die frisch gelesene untere Grenze
bleibt erhalten; das Ergebnis wird zurückgelesen. Ohne ausdrücklich gelieferte
obere Grenze oder bei einem nicht unterstützten Einstellungsweg bleibt der
Regler unverfügbar. Siehe
[Unterstützung und Testhinweise](docs/battery-charge-limit.md).

## Neu in Beta v0.5.2b2: Batterieheizung, Licht und Display

Die Beta v0.5.2b2 ergänzt **Batterieheizung erlauben**, einen RGB-Leuchtstreifen
mit Helligkeit, Displayhelligkeit sowie getrennte Ausschaltzeiten für Licht und
Display. Unter **Konfigurieren** die neue Option **Gerätesteuerung freigeben**
einschalten; sie ist unabhängig von der Batteriesteuerung und standardmäßig aus.
Danach werden unterstützte Einstellungen alle 30 Minuten gelesen und können
über einen eigenen Aktualisierungsknopf erneut abgerufen werden.

Die Heizungsfreigabe erlaubt die automatische Erwärmung durch das Gerät; sie
erzwingt kein Heizen und zeigt keine aktive Heizung an. Benannte App-Lichteffekte
wie „Regenbogen“ werden noch nicht angeboten. Nicht bestätigte Funktionen bleiben
unverfügbar. Jede Änderung liest zuerst die aktuellen Einstellungen und prüft
das Ergebnis anschließend. Gerätetests stehen noch aus; siehe
[Funktionsumfang und Testhinweise](docs/device-settings.md).

## Anzeige des Batteriemodus (v0.5.2 Beta)

Der Batteriemodus-Sensor verwendet übersetzte Zustände mit festen Kennungen wie
`self_consumption` und `time_of_use`. Seine Entitäts-ID bleibt erhalten. Beim
Installieren dieser Beta Automationen und Templates anpassen,
die diesen Sensor mit dem bisherigen englischen Text (z. B. `Self-Consumption`)
vergleichen. Die Auswahlwerte für Batteriebefehle bleiben auf Englisch erhalten.

## Installation mit HACS / Marketplace

**Hoymiles S-Miles Home ist offiziell im [HACS-Standardkatalog](https://github.com/hacs/default/blob/master/integration) gelistet.** Die Integration lässt sich direkt über die HACS-Suche installieren; ein benutzerdefiniertes Repository ist nicht mehr erforderlich. Sie bleibt eine inoffizielle Hoymiles-Integration.

1. Ab HA 2026.11 **Einstellungen → Marketplace** öffnen. Bis HA 2026.10
   HACS installieren, falls noch nicht vorhanden, und HACS öffnen.
2. Nach **Hoymiles S-Miles Home** suchen und die Integration installieren. Beta-Versionen sind nicht erforderlich.
3. Home Assistant neu starten.
4. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach
   **Hoymiles S-Miles Home** suchen. Die E-Mail-Adresse und das Passwort des
   S-Miles-Home-Kontos eingeben und anschließend die Anlage auswählen.
   Für die manuelle Einrichtung siehe [Station-ID finden](#station-id-finden).

Weitere Veröffentlichungen stehen über HACS bereit. Bestehende Installationen,
die über ein benutzerdefiniertes Repository eingerichtet wurden, können die
Integration weiterverwenden; die HA-Konfiguration muss nicht neu angelegt werden.

## Beta-Versionen testen

Für den Alltag empfehlen wir Stable; freiwillige Betatester können weiterhin
Vorabversionen auswählen. Vorher die [Release-Hinweise](https://github.com/Phil-0805/hoymiles-home-assistant/releases)
der gewählten Version lesen und eine Sicherung erstellen.

- **Ab HA 2026.11 / Marketplace:** Unter **Einstellungen → Geräte & Dienste → Marketplace**
  die Geräteseite dieses Repositorys öffnen. Die standardmäßig deaktivierte
  Schalter-Entität **Pre-release** aktivieren und anschließend einschalten.
  Die angebotene Beta installieren oder auf der Repositoryseite über **Andere
  Version installieren** eine Beta wie `0.5.2b2` auswählen.
- **Bis HA 2026.10 / HACS:** Dieses Repository öffnen, Vorabversionen aktivieren
  und über **Erneut herunterladen** die Beta auswählen. Die Beschriftung kann
  je nach HACS-Version abweichen.

Danach Home Assistant neu starten; vorhandene Integration und Entitäten behalten.
Messwerte anhand des [Gerätetestplans](docs/testing-0.5.0.de.md) mit der App
vergleichen. Bei Problemen Beta-/HA-Version, Gerätemodell und Beobachtung im
Issue nennen; keine Zugangsdaten, Tokens, Seriennummern oder privaten Screenshots
veröffentlichen. Tests von Batteriebefehlen sind freiwillig und benötigen die
Freigabe der Batteriesteuerung.

Zum Verlassen des Betakanals Vorabversionen deaktivieren. Für eine sofortige
Rückkehr die Sicherung von vor dem Betatest wiederherstellen; siehe die
[Marketplace-Hinweise zum Versionswechsel](https://www.home-assistant.io/integrations/marketplace/#installing-another-version).
Automationen werden bei geänderten Sensorzuständen nicht automatisch angepasst.

## Manuelle Installation

Die ZIP-Datei der Veröffentlichung entpacken und den Ordner
`custom_components/hoymiles_home` als `custom_components/hoymiles_home` in
das Konfigurationsverzeichnis von Home Assistant kopieren.
Home Assistant neu starten und **Hoymiles S-Miles Home** unter
**Einstellungen → Geräte & Dienste** hinzufügen.

## Station-ID finden

Für die Einrichtung wird die numerische **Station-ID** (`sid`) der Anlage
benötigt. Die Seriennummer des Wechselrichters und die numerische `id`
eines einzelnen Geräts sind andere Kennungen.

1. [S-Miles Cloud](https://global.hoymiles.com) in einem Desktop-Browser öffnen
   und anmelden.
2. **Anlage** (**Plant** auf Englisch) öffnen und die eigene Anlage auswählen.
3. Auf der Detailseite die Adressleiste prüfen. Der Maintainer hat bestätigt,
   dass sich die Station-ID aus der URL der ausgewählten Anlage entnehmen lässt:
   `https://global.hoymiles.com/website/plant/detail/<station-id>`.
   Die numerische Station-ID in das Einrichtungsformular von Home Assistant kopieren.
4. Zur Orientierung: Oben links, direkt unter dem Anlagennamen, zeigt das
   Portal ebenfalls eine ID an. Beim Maintainer lautet die deutsche
   Beschriftung **Mikro-Energiespeicher ID**. Ein Nutzer in
   [Issue #2](https://github.com/Phil-0805/hoymiles-home-assistant/issues/2)
   nennt dagegen **PV microinverter ID**. Nicht pauschal davon ausgehen,
   dass jedes Feld mit einer dieser Beschriftungen die API-Station-ID enthält;
   den bestätigten Wert aus der URL verwenden.

Wer für diese Anlage bereits erfolgreich den Node-RED-Node `hoymiles-watch`
verwendet, kann dessen konfigurierten `sid` übernehmen. Node-RED ist nicht
erforderlich.

Bei der Einrichtung wird geprüft, ob das angemeldete Konto für die eingegebene
ID eine nicht leere Geräteliste abrufen kann. Anschließend prüfen, ob Geräte
und Messwerte zur eigenen Anlage passen. Falls die URL anders aufgebaut ist
oder keine numerische Station-ID erkennbar ist, in Issue #2 nachfragen,
anstatt eine Seriennummer einzutragen. Niemals Passwörter, Login-Tokens oder
ungeschwärzte Diagnosedaten in einem öffentlichen Issue veröffentlichen.

## Was zu erwarten ist

- Ab Version 0.4.2 liest die Modellerkennung `model_no` und fragt bei fehlender
  Modellangabe optional ausführlichere Web-Gerätedaten ab. Manche Konten haben
  darauf keinen Zugriff. Falls die Modellanzeige allgemein bleibt, die
  Integrationsdiagnose unter **Einstellungen → Geräte & Dienste** herunterladen;
  der Abschnitt `inverters` enthält nur Modellergebnis und Abrufstatus.
- Die Modellanzeige verwendet eine eindeutige HMS-Modellnummer aus den
  Gerätedaten, andernfalls "Hoymiles microinverter". Bei bekannten Modellen
  wird die physische Anzahl der PV-Eingänge verwendet. Ohne Modellangabe bleiben
  die bisherigen Diagrammabfragen für vier Eingänge erhalten; daraus folgt keine
  Erkennung von vier Eingängen oder 2000 W. Geräte- und Sensor-Kennungen bleiben erhalten.
- Aktuelle Daten folgen dem von Hoymiles vorgegebenen Intervall, normalerweise
  etwa drei Sekunden. Moduldiagrammwerte werden üblicherweise alle fünf Minuten
  aktualisiert. Dies ist Cloud-Polling und keine Garantie für Echtzeitdaten
  direkt vom Wechselrichter.
- Batterie-Entitäten und -Steuerungen sind nur mit einer unterstützten Batterie
  sinnvoll. Ein Mikrowechselrichter ohne Speicher erhält dadurch keine
  Batteriemesswerte.
- Die tägliche Lade- und Entladeenergie sowie der tägliche Hausverbrauch werden
  lokal aus Leistungswerten berechnet. Kurze Ausfälle können Lücken verursachen;
  diese Werte sind nicht für Abrechnungszwecke geeignet.
- Der Reserve-SOC ist der eingestellte Mindestladezustand, nicht der aktuelle
  Ladezustand. Änderungen werden über Hoymiles an das Gerät gesendet und können
  erst nach einigen Sekunden sichtbar sein. Nach einer Änderung die
  S-Miles-Home-App kontrollieren.

## Datenschutz und Sicherheit

Die Integration übermittelt die Zugangsdaten per HTTPS an Hoymiles und verwendet
anschließend einen Kontotoken, um Daten von Hoymiles-Endpunkten abzurufen.
Messwerte und Zugangsdaten werden weder an dieses GitHub-Projekt noch an einen
zusätzlichen Analysedienst gesendet. Das Passwort wird lokal im
Konfigurationseintrag von Home Assistant gespeichert, damit die Integration
erneut eine Verbindung herstellen kann. Home-Assistant-System und Backups
entsprechend schützen. Die Lösung ist **nicht** durchgehend privat oder
unabhängig geprüft: Hoymiles verarbeitet die Anlagendaten bereits, und die
undokumentierte API kann sich ändern. Der Token wird nur an HTTPS-Hosts von
Hoymiles gesendet; Weiterleitungen und unerwartete Hosts für aktuelle Daten
werden abgelehnt. Home Assistant nur mit den üblichen Zugriffsschutzmaßnahmen
öffentlich erreichbar machen.

## Hinweise

- Diese Integration verwendet eine inoffizielle Cloud-API und steht nicht in Verbindung mit Hoymiles.
- Zusätzliche Wechselrichterwerte und Batterietemperaturen lassen sich unter
  **Konfigurieren** aktivieren. Sie sind zunächst ausgeschaltet und können anfangs nicht verfügbar sein.
- Änderungen an Batteriemodus oder Reserve-SOC senden einen echten Steuerbefehl.
  Gleichzeitige Änderungen in der App vermeiden und dort das Ergebnis prüfen.

Weitere Details stehen in den [Release-Hinweisen und bekannten Einschränkungen](docs/release-0.5.1.md)
und im [Gerätetestplan](docs/testing-0.5.0.de.md).
