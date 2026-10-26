# Hoymiles S-Miles Home für Home Assistant

[English](README.md) | **Deutsch**

Inoffizielle Home-Assistant-Integration für **S-Miles-Home**-Konten. Sie liest
Daten direkt aus der Hoymiles-Cloud; Node-RED, MQTT und lokaler Zugriff auf den
Wechselrichter sind nicht erforderlich. Entwickelt und getestet mit einem
HMS-2000-4WB mit HiBattery. Ein Nutzer hat außerdem den erfolgreichen Einsatz
mit einem 800-W-Mikrowechselrichter gemeldet. Dieses Modell und die verfügbaren
Sensoren wurden hier jedoch noch nicht unabhängig überprüft.

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

## Installation mit HACS

1. Falls noch nicht vorhanden, HACS installieren und **HACS → Integrationen** öffnen.
2. Im HACS-Menü **Benutzerdefinierte Repositories** öffnen.
3. `https://github.com/Phil-0805/hoymiles-home-assistant` mit der Kategorie
   **Integration** hinzufügen.
4. **Hoymiles S-Miles Home** installieren. Beta-Versionen müssen **nicht** aktiviert werden.
5. Home Assistant neu starten.
6. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach
   **Hoymiles S-Miles Home** suchen. Die E-Mail-Adresse und das Passwort des
   S-Miles-Home-Kontos sowie die numerische Station-ID eingeben
   (siehe [Station-ID finden](#station-id-finden)).

Weitere Veröffentlichungen können anschließend über HACS angeboten werden.
Die Integration ist nicht im HACS-Standardkatalog enthalten; das
benutzerdefinierte Repository muss weiterhin hinzugefügt werden.

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

Dieses Projekt verwendet eine inoffizielle Cloud-API und steht in keiner
Verbindung zu Hoymiles. Der schnelle Endpunkt für aktuelle Daten folgt der vom
Server vorgegebenen Wartezeit. Modulwerte werden alle fünf Minuten aktualisiert.
Für dieselbe Anlage nur dann einen weiteren schnellen Cloud-Poller aktivieren,
wenn dies zur Diagnose erforderlich ist.

Die Diagnosewerte `ems`, `brs`, `chs` und `bhs` werden unverarbeitet
angezeigt, da Hoymiles nicht für jeden numerischen Zustand eine verlässliche
Bedeutung veröffentlicht. Beim getesteten HMS-2000-4WB beschreibt `brs` die
Batterierichtung (`1` Laden, `2` Entladen, `0` Leerlauf), während
`power.bat` den vorzeichenlosen Betrag der Leistung enthält.

Die Batteriesteuerung nutzt die inoffizielle asynchrone Cloud-API von Hoymiles
für Einstellungen. Änderungen am Reserve-SOC oder Modus senden einen echten
Steuerbefehl an die HiBattery. Die Integration erhält den vollständigen
Einstellungsblock des gewählten Modus und liest ihn nach jedem Schreibvorgang
zurück. Undokumentierte, nur im Backend vorhandene Modi werden nicht als
einstellbare Auswahl angeboten.
