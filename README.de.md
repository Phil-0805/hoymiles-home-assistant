# Hoymiles S-Miles Home für Home Assistant

[![HACS Default](https://img.shields.io/badge/Marketplace%20%7C%20HACS-Default-orange)](https://github.com/hacs/default/blob/master/integration)
[![Release](https://img.shields.io/github/v/release/Phil-0805/hoymiles-home-assistant)](https://github.com/Phil-0805/hoymiles-home-assistant/releases/latest)
[![Last commit](https://img.shields.io/github/last-commit/Phil-0805/hoymiles-home-assistant/main?label=last%20commit%20%28main%29)](https://github.com/Phil-0805/hoymiles-home-assistant/commits/main)
[![Tests](https://img.shields.io/github/actions/workflow/status/Phil-0805/hoymiles-home-assistant/tests.yml?branch=main&label=tests%20%28main%29)](https://github.com/Phil-0805/hoymiles-home-assistant/actions/workflows/tests.yml)
[![HA tested](https://img.shields.io/badge/HA%20tested-2026.10.4%20%7C%202026.11.0-blue)](https://github.com/Phil-0805/hoymiles-home-assistant/actions/workflows/tests.yml)
[![Release downloads](https://img.shields.io/github/downloads/Phil-0805/hoymiles-home-assistant/total?label=release%20downloads)](https://github.com/Phil-0805/hoymiles-home-assistant/releases)
[![License MIT](https://img.shields.io/github/license/Phil-0805/hoymiles-home-assistant)](LICENSE)

[English](README.md) | **Deutsch**

Verbinde dein **S-Miles-Home-Konto** mit Home Assistant, um deine Solaranlage und
unterstützte Batterieeinstellungen über die Hoymiles-Cloud einzubinden.
Node-RED oder ein MQTT-Broker sind nicht erforderlich. Das Community-Projekt
ist unabhängig von Hoymiles und offiziell im HACS-Standardkatalog gelistet.

**v0.6.0** bringt die kontobasierte Anmeldung, getrennte Batterie-Schlussstufen
und Licht-/Displaysteuerung in den Stable-Kanal. Die Version bündelt die Fixes
aus den v0.5.2-Betas und v0.6.0b1. Bestehende Installationen können direkt aktualisiert werden.

[Neu in v0.6.0](docs/release-0.6.0.md) · [Upgrade-Hinweise](#update-auf-060)

[Installation](#installation) · [Funktionen](#funktionen) · [Steuerung](#steuerung) ·
[Betatest](#beta-versionen-testen) · [Probleme](#probleme-untersuchen)

## Installation

1. HACS / Marketplace öffnen und nach **Hoymiles S-Miles Home** suchen.
   Die Integration ist im Standardkatalog; ein benutzerdefiniertes Repository
   muss nicht hinzugefügt werden.
2. Integration installieren und Home Assistant neu starten.
3. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen**
   **Hoymiles S-Miles Home** auswählen.
4. E-Mail-Adresse und Passwort des S-Miles-Home-Kontos eingeben und die Anlage
   auswählen. Für eine weitere Anlage die Integration erneut hinzufügen.

Falls die Anlagensuche nicht verfügbar ist, die numerische Station-ID manuell
eingeben. Siehe [Station-ID finden](#station-id-finden). Bei Updates müssen
vorhandene Integration und Entitäten nicht neu angelegt werden.

## Funktionen

Die Verfügbarkeit hängt von Gerät, Firmware und Cloud-Antwort ab.

| Bereich | Funktionen |
| --- | --- |
| Aktuelle Daten | PV-, Netz-, Hausverbrauchs- und Batterieleistung; Verbindungsstatus und Batterieladezustand |
| Energie | Gelieferte Energiezähler der Anlage; lokal berechnete tägliche Lade-, Entlade- und Hausverbrauchsenergie |
| PV-Module | Leistung, Spannung und Strom aus Fünf-Minuten-Diagrammen; wählbare PV-Datenquelle |
| Batterie | Modus, Reserve-SOC und schreibgeschützte Statusdiagnose |
| Batteriesteuerung | Automatische Temperaturabfrage und getrennte Lade-/Entladeschlussstufen |
| Geräteeinstellungen | Freigabe automatischer Batterieheizung, LED-Farbe/-Helligkeit, Displayhelligkeit und getrennte Ausschaltverzögerungen |
| Ausgangsleistung | Watt-Regler bei vollständigen Cloud-Einstellungen, Grenzen und Phasenangaben; Gerätebestätigung noch offen |
| Diagnose | Fehlerstelle und Fehlergrund bei Login-/Verbindungsproblemen sowie Wiederherstellungsversuch bei fehlender Live-Serveradresse |

Live-Abfragen folgen dem von Hoymiles vorgegebenen Intervall, normalerweise etwa
drei Sekunden. Moduldiagramme und Batterietemperaturen werden ungefähr alle fünf
Minuten aktualisiert. Einstellungen werden normalerweise alle 30 Minuten gelesen
und haben manuelle Aktualisierungsknöpfe. Vorübergehend fehlgeschlagene Leseabrufe
erhalten höchstens zwei zusätzliche Versuche nach einer und dann drei Minuten.
Anmeldefehler, Abruflimits und ungültige Einstellungen behalten ihre bisherige
Behandlung. Die Verfügbarkeit der Cloud kann sämtliche Messwerte beeinflussen.

## Steuerung

Unter **Einstellungen → Geräte & Dienste → Hoymiles S-Miles Home → Konfigurieren**:

| Option | Aktiviert |
| --- | --- |
| **Batteriesteuerung freigeben** | Batteriemodus, Reserve-SOC, getrennte Schlussstufen und unterstützte Ausgangsleistungseinstellungen |
| **Gerätesteuerung freigeben** | Heizungsfreigabe, LED- und Displayeinstellungen |
| **Zusätzliche Wechselrichter-Messwerte (Beta)** | Optionale Wechselrichtertemperatur, Frequenz und AC-Spannung, soweit verfügbar |

Schreibzugriffe sind standardmäßig deaktiviert. Änderungen lesen zuerst die
aktuellen Einstellungen, erhalten zugehörige Werte und prüfen das Ergebnis durch
Rücklesen. Nach einer Änderung die App kontrollieren; gleichzeitige Änderungen
über App und HA vermeiden.

- **Reserve-SOC und Entladeschlussstufe sind getrennte Einstellungen.** Siehe
  [Details zu den Schlussstufen](docs/battery-charge-limit.md).
- **Heizungsfreigabe** erlaubt automatisches Heizen; sie erzwingt kein Heizen
  und zeigt keine Heizaktivität an. Benannte Lichteffekte werden nicht angeboten.
  Siehe [Geräteeinstellungen](docs/device-settings.md).
- **Ausgangsleistung** benötigt ausdrücklich gelieferte Cloud-Grenzen. Ein
  unverfügbarer Regler belegt keinen Gerätedefekt. Die separate zulässige
  Obergrenze und die Netzeinspeisegrenze werden dadurch nicht verändert.
  Siehe [Details zur Ausgangsleistung](docs/output-power-settings.md).

## Gerätekompatibilität

| Aufbau | Bisherige Bestätigung |
| --- | --- |
| HMS-2000-4WB mit HiBattery | Aufbau des Maintainers; Modell-/PV-Anzeige und ausgewählte Batterie-/Gerätesteuerungen getestet |
| HMS-800-2WB | Modell- und PV-Anzeige bestätigt; Batterie-/Geräteeinstellungen können sich zwischen Anlagen unterscheiden |
| HiBattery 4020-X mit einem Zusatzspeicher | Nutzer bestätigt gewählte PV-Quelle, Temperaturen, Relaisrichtung und Batteriebefehle unter v0.5.1; [Issue #9](https://github.com/Phil-0805/hoymiles-home-assistant/issues/9) |

Diese Beobachtungen bestätigen nicht jede Einstellung oder Firmware. Der
Tests-Badge zeigt `main`; der HA-Badge nennt Versionen der aktuellen Testmatrix,
keine HA-Mindestversion. Modellnamen stammen aus eindeutigen Gerätedaten,
andernfalls bleibt die Anzeige allgemein. Fehlende Werte bleiben unverfügbar.
Batterie-Entitäten liefern nur mit unterstütztem Speicher sinnvolle Daten.
Berechnete Tagesenergien können bei Ausfällen Lücken enthalten und sind nicht
für Abrechnungszwecke geeignet.

## Update auf 0.6.0

Hinweise der gewählten Veröffentlichung lesen, Update installieren und Home
Assistant neu starten. Bestehende Konfigurationseinträge und Entitäten behalten.

- Der Batteriemodus-Sensor verwendet Kennungen wie `self_consumption` und
  `time_of_use`, die übersetzt angezeigt werden. Templates mit Vergleichen auf
  den früheren englischen Sensortext anpassen. Befehlsauswahlwerte bleiben gleich.
- Der falsch zugeordnete Ladegrenzen-Regler aus b2 und sein Sensor entfallen.
  Betroffene Automationen bewusst auf die getrennten App-Schlussstufen umstellen.
- Batterietemperaturen benötigen die bisherige Freigabe nicht mehr.
  Zusätzliche Wechselrichterwerte bleiben optional.
- Der alte Sensor **Maximale Leistungseinstellung (Rohwert)** entfällt.
  Verweise in Dashboards oder Automationen anpassen; der Ausgangsleistungs-Regler bleibt.

## Beta-Versionen testen

Für den Alltag empfehlen wir Stable; freiwillige Betatester können weiterhin
Vorabversionen auswählen. Vorher die [Release-Hinweise](https://github.com/Phil-0805/hoymiles-home-assistant/releases)
der gewählten Version lesen und eine Sicherung erstellen.

- **Ab HA 2026.11 / Marketplace:** Unter **Einstellungen → Geräte & Dienste → Marketplace**
  die Geräteseite dieses Repositorys öffnen. Die standardmäßig deaktivierte
  Schalter-Entität **Pre-release** aktivieren und anschließend einschalten.
  Die angebotene Beta installieren oder auf der Repositoryseite über **Andere
  Version installieren** eine Beta wie `0.6.0b1` auswählen.
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

## Probleme untersuchen

Installierte Integrationsversion, HA-Version sowie Gerät und Firmware prüfen.
Bei Login-/Verbindungsfehlern unter **Einstellungen → System →
Protokolle → Home Assistant Core** nach `hoymiles_home.cloud_logging` suchen.
Warnungen nennen `stage`, `reason` und gegebenenfalls numerische Statuscodes.
Debug-Logging ist nicht erforderlich. Siehe [Verbindungstest](docs/release-0.6.0.md).
Fehlende Live-Serveradresse und fehlgeschlagener Login können verschiedene
Ursachen haben. Bei ausbleibenden Messwerten mit der offiziellen App vergleichen.
Sind beide betroffen, kann eine gemeinsame Geräte-/Cloud-Störung vorliegen;
die konkrete Ursache ist damit noch nicht geklärt. Nach einem vorübergehenden
Startfehler kann das Nachladen der Einstellungen einige Minuten dauern.

Bei Loginmeldungen die genaue getestete App nennen: **S-Miles Home** und
**S-Miles Installer** sind unterschiedliche Clients. Ein erfolgreicher
Installer-/Weblogin bestätigt keinen Zugriff über die Home-API. Die Beta
v0.6.1b11 enthält die anfängliche Kontoroute, verbesserte TOU-Modusanzeige,
das Aktivieren unterstützter vorhandener Basispläne und stellt die begrenzte Live-Wiederherstellung nach der b5-Regression wieder her und erlaubt den Anlagenstart bei fehlender Live-Serveradresse; siehe
[Testanleitung](docs/release-0.6.1b11.md) und
[Befunde und offene Grenzen](docs/login-routing-0.6.1.md).
B10 korrigiert außerdem Home-DTU-Verschachtelungen und Chartzeiten, behält
bestätigte Leistungsgrenzen über Nacht bei und entfernt die separate letzte Temperatur.
B11 korrigiert die Chart-Verfügbarkeit zwischen normalen Abrufen, erhält die
ursprünglichen Messzeiten und lässt stehengebliebene Daten weiterhin ablaufen.

Die Diagnose der betroffenen Integration unter **Geräte & Dienste** herunterladen.
Version, betroffene Einstellung und den passenden App-Vergleich in einem
[Issue](https://github.com/Phil-0805/hoymiles-home-assistant/issues) angeben.
Keine Zugangsdaten, Tokens, Seriennummern oder ungeschwärzten Screenshots
veröffentlichen.

## Manuelle Installation

Enthält die Veröffentlichung **hoymiles_home.zip**, dessen Inhalt direkt nach
`<config>/custom_components/hoymiles_home/` entpacken; dort muss unmittelbar
`manifest.json` liegen. Bei einem GitHub-Archiv **Source code (zip)** oder älteren
Releases den enthaltenen Ordner `custom_components/hoymiles_home` nach
`<config>/custom_components/` kopieren. Home Assistant neu starten und die
Integration unter **Geräte & Dienste** hinzufügen.

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

## Datenschutz

Zugangsdaten werden per HTTPS an Hoymiles gesendet. Das Passwort liegt für die
erneute Anmeldung im lokalen HA-Konfigurationseintrag; System und Backups
entsprechend schützen. Kontotokens werden nur an HTTPS-Hosts von Hoymiles
übermittelt. Beim Login ist eine Weiterleitung auf denselben Auth-Pfad eines
ausdrücklich zugelassenen HTTPS-API-Hosts möglich, ohne den bisherigen Token
weiterzugeben. Andere API-Weiterleitungen bleiben gesperrt. Messwerte und Zugangsdaten gehen
weder an dieses Projekt noch an einen zusätzlichen Analysedienst. Neue
Cloud-Diagnoselogs enthalten feste Kennungen und Strukturangaben statt
Rohantworten, Gerätekennungen oder Zugangsdaten.

Die Cloud-API ist undokumentiert und kann sich ändern. Das Projekt ist nicht
unabhängig geprüft.

[MIT-Lizenz](LICENSE) · [Release-Hinweise](https://github.com/Phil-0805/hoymiles-home-assistant/releases) ·
[Gerätetestplan](docs/testing-0.5.0.de.md) · [MQTT-Prüfung für v0.7.0](docs/roadmap-0.7.md)

### Installer-Kontoprofil (experimentell)

Beta **v0.6.1b3** ergänzt den ausdrücklich wählbaren Kontotyp **S-Miles Installer**
bei Einrichtung und Wiederanmeldung. Er umfasst Live-Messwerte,
Energiewerte und Geräteidentität/Modell. Home-Steuerungen, Temperaturen,
Moduldiagramme und zusätzliche Telemetrie werden dafür nicht freigegeben.
Siehe [Protokollbefunde und Testumfang](docs/installer-app-protocol.md).
