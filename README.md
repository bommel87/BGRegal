# BGRegal

*English version: [README.en.md](README.en.md)*

BGRegal bringt deine BoardGameGeek-Sammlung nach Home Assistant und steuert den Spieleabend: virtuelles Regal,
NFC-Tag je Spiel, Licht- und Soundprofil, Spielhilfe während der Partie, Übergabe an BG Stats, Spielvorschlag,
Spieleabend-Planung mit Abstimmung, Statistik, Pile of Shame, Wunschliste, Verleih und Regelfragen per HA Assist.

**BGG ist die Quelle, BG Stats der Ort für Partien.** BGRegal liest nur von BGG und schreibt nie dorthin. Eine Partie
übergibst du am Ende per QR-Code an BG Stats; BG Stats überträgt sie zu BGG, und beim nächsten Sync erscheint sie in
BGRegal. Lokal speichert BGRegal nur, was BGG nicht kennt: Standort, NFC-Tag, Profile, Verleih, Mitspieler-Vorlieben
und Spieleabende.

## Installation

1. HACS → *Benutzerdefinierte Repositories* → `https://github.com/bommel87/BGRegal`, Kategorie *Integration*.
   Ohne HACS: den Ordner `custom_components/bgregal` nach `/config/custom_components/` kopieren.
2. Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → BGRegal*.
   BGG verlangt für die XML-API einen **API-Token**; du erstellst ihn unter
   [boardgamegeek.com/applications](https://boardgamegeek.com/applications).
4. In der Seitenleiste erscheint **BGRegal**. Der erste Sync lädt Sammlung, Spielinfos und alle Partien und kann
   einige Minuten dauern.

### Optionen

| Option | Standard | Wozu |
| --- | --- | --- |
| Sync-Intervall | 6 h | Abstand zwischen zwei Abgleichen mit BGG |
| Standard-Wiedergabegerät | – | spielt die Playlist eines Spiels während der Sitzung |
| Szene bei Sitzungsende | – | z. B. wieder normales Licht |
| Verleih-Erinnerung nach | 60 Tagen | danach alle 30 Tage erneut |
| „Lange nicht gespielt“ ab | 24 Monaten | für Statistik und Spielvorschlag |
| Zusätzlich benachrichtigen | – | z. B. `notify.mobile_app_handy`; sonst nur HA-Benachrichtigung |

## Das Panel

| Bereich | Inhalt |
| --- | --- |
| **Regal** | Regale nach Raum gruppiert, Fächer mit allen Schachteln. Suche und Filter heben Treffer hervor, statt Spiele auszublenden. |
| **Spiel-Fenster** | Infos, letzte Partien, Erweiterungen; Standort, NFC-Tag, EAN, Licht, Sound, Anleitung; Anleitungen als PDF; verleihen; Sitzung starten |
| **Sitzung** | Laufzeit, Runde, wer am Zug ist; danach Mitspieler, Punkte, Gewinner und QR-Code für BG Stats |
| **Vorschlag** | Filter nach Spielerzahl, Modus, Typ, Dauer und Anwesenden; Ja/Nein; Standort |
| **Spieleabende** | Termin, Gäste, Spiele zur Wahl, Abstimm-Link und QR-Code, Rangliste |
| **Mitspieler** | aus deinen BGG-Partien plus selbst angelegte, mit BGG-Name und Vorlieben; ausblendbar |
| **Statistik** | Partien pro Monat, meistgespielt, lange nicht gespielt, H-Index |
| **Pile of Shame** | alle eigenen Spiele ohne eine einzige Partie |
| **Wunschliste** | Wunschliste von BGG und neue Erweiterungen zu deinen Spielen |
| **Verliehen** | was an wen seit wann verliehen ist |

### Regale und Räume

Regal und Fach trägst du im Spiel-Fenster ein. Fach 1 ist das oberste. Eine Erweiterung kann in einem Karton liegen,
im eigenen Basisspiel oder in jedem anderen Spiel der Sammlung („Liegt im Karton von“). Dann steht sie nicht extra im
Regal: Sie hat den Standort des Kartons und zieht mit um. Die Kachel des Kartons zeigt die Zahl der Erweiterungen, sein
Spiel-Fenster listet sie, und die Suche nach der Erweiterung hebt den Karton hervor. Ein Karton, der selbst in einem
Karton liegt, nimmt nichts auf.

Die Regale stehen nach Raum gruppiert untereinander. Unter **Regal einstellen** legst du fest:

- **Raum:** ein Bereich aus Home Assistant. Jedes Regal ist ein eigenes Gerät in diesem Raum, mit einem Sensor für die
  Zahl der Spiele. Änderst du den Raum am Gerät in Home Assistant, übernimmt BGRegal ihn.
- **Fächer:** wie viele Fächer das Regal hat, auch leere, und ob Fach 1 oben oder unten ist.
- **Spiele sortieren nach:** Name, Partien, letzte Partie oder eigene Reihenfolge.
- **Name:** Umbenennen ändert den Standort aller Spiele darin.

**Sortieren** in der Regalansicht schaltet Pfeile ein: ▲▼ verschieben Räume und Regale, ◀▶ verschieben Spiele in
Regalen mit eigener Reihenfolge. Die Reihenfolge speichert die Integration, sie gilt also auf allen Geräten. Bei der
Inventur wird die Scan-Reihenfolge gleich als eigene Reihenfolge im Fach übernommen.

Suchst du ein Spiel oder wählst einen Filter, bleiben alle Regale sichtbar: Treffer bekommen einen farbigen Rahmen,
alles andere wird blass, und die Ansicht springt zum ersten Treffer.

### NFC

Tag an die Schachtel kleben, mit der Home-Assistant-App scannen und im Spiel-Fenster **Gescannten übernehmen**
drücken (gilt für den Tag der letzten 10 Minuten). Danach gilt:

- **Scan** startet die Sitzung: Lichtprofil (Szene oder Skript) und Playlist laufen an.
- **Zweiter Scan** desselben Tags beendet sie: Musik pausiert, die Szene für Sitzungsende läuft.

### Inventur: Regal per Scan einräumen

Unter *Regal* startet **Inventur** das Durchscannen eines Regals. Du wählst das Regal (auch ein neues) und das Fach,
bei dem du anfängst. Dann scannst du die Spiele dieses Fachs nacheinander: BGRegal trägt Regal und Fach sofort ein.
Es funktioniert mit Kamera, Barcode-Scanner oder NFC-Tag.

- Unter dem Scanfeld steht die Liste des Fachs, **Rückgängig** setzt den letzten Scan zurück.
- Spiele ohne Code fügst du per Name hinzu; einen unbekannten Barcode ordnest du einmal zu, danach steht das Spiel im Fach.
- **Nächstes Fach** schaltet weiter, **Fertig** beendet. Standen laut BGRegal Spiele im Fach, die du nicht gescannt
  hast, fragt BGRegal, ob sie auf „Ohne Standort“ gesetzt werden.
- Während der Inventur starten Scans keine Sitzung, auch NFC-Tags aus der Home-Assistant-App nicht. Nach 10 Minuten
  ohne Scan endet die Inventur von selbst.

### EAN-Barcode

Statt eines NFC-Tags (oder zusätzlich) kannst du den Barcode auf der Schachtel nutzen. Oben im Panel öffnet das
Barcode-Symbol den Scanner:

- **Kamera:** funktioniert in Chrome auf Android und am Rechner mit Kamera. Safari auf dem iPhone kann keine Barcodes
  lesen.
- **Barcode-Scanner (USB/Bluetooth):** scannt wie eine Tastatur in das Feld „Code“.

Ein bekannter Code startet oder beendet die Sitzung wie ein NFC-Tag. Bei einem unbekannten Code fragt BGRegal, zu
welchem Spiel er gehört, und merkt ihn sich. Im Spiel-Fenster kannst du die EAN auch eintragen oder per Kamera
übernehmen. Für eigene Scanner gibt es den Dienst `bgregal.scan_code`.

### Spieleabend und Abstimmung

Beim Anlegen wählt BGRegal bis zu acht passende Spiele für die Zahl der Gäste aus und berücksichtigt deren
Vorlieben. Die Auswahl kannst du ändern. Jeder Abend bekommt einen geheimen Link mit QR-Code auf eine kleine
Abstimmseite. Gäste brauchen **kein** Home-Assistant-Konto; wer den Link hat, kann nur für diesen Abend abstimmen.
Im WLAN funktioniert der Link immer, von unterwegs nur, wenn Home Assistant von außen erreichbar ist
(z. B. über Nabu Casa). Abstimmen geht bis 6 Uhr am Morgen nach dem Abend.

### Regelfragen mit HA Assist

Im Spiel-Fenster lädst du unter **Anleitungen (PDF)** die Anleitung hoch, auch mehrere je Spiel (Regelheft,
Almanach). Während der Sitzung erscheinen sie als Knöpfe auf der Sitzungskarte.

Für Fragen brauchst du einen Assist-Agenten mit LLM, z. B. die Anthropic-Integration mit eigenem API-Key. Beim Agenten
unter *Konfigurieren → Steuern von Home Assistant* **Spielregeln (BGRegal)** anhaken. Dann fragst du in Assist
etwa „Darf ich in Catan den Räuber auf die Wüste setzen?“. Ohne Spielnamen ist das Spiel der laufenden Sitzung
gemeint. Das LLM antwortet nur aus der Anleitung, mit Seitenangabe, und sagt, wenn dort nichts dazu steht.

BGRegal liest den Text beim ersten Abruf aus und speichert ihn zwischen. Gescannte PDFs ohne Textebene kann es nicht
lesen; die vorher per OCR umwandeln. Höchstens 100 MB je Datei.

Unter den PDFs trägst du beliebig viele **Links** ein, etwa zu Errata, FAQ oder Almanach (Titel und Adresse,
dann **Speichern**). Sie erscheinen als Knöpfe im Spiel-Fenster und auf der Sitzungskarte. Assist liest Webseiten
und PDFs hinter den Links mit; Errata gehen der Anleitung vor. Der Text wird 7 Tage zwischengespeichert. Seiten
hinter einem Login oder solche, die ihren Inhalt erst per JavaScript laden (z. B. BGG-Foren), liefern oft keinen Text.

## Dashboard-Kachel

```yaml
type: custom:bgregal-card
bgg_id: 13      # optional; ohne: das Spiel der laufenden Sitzung, sonst der aktuelle Vorschlag
title: Catan    # optional
```

Die Kachel zeigt Cover, Partienzahl, letzte Partie und Standort, dazu einen Start-Knopf oder die Laufzeit.

## Entitäten

| Entität | Zustand | Attribute |
| --- | --- | --- |
| `sensor.bgregal_sammlung` | Anzahl Spiele | Erweiterungen, Pile of Shame, lange nicht gespielt |
| `sensor.bgregal_partien` | Partien gesamt | diesen Monat, H-Index, letzte Partie |
| `sensor.bgregal_sitzung` | `idle` / `running` / `finished` | Spiel, Start, Runde, am Zug, Reihenfolge, Standort |
| `sensor.bgregal_vorschlag` | `idle` / `suggested` / `accepted` / `none` | Spiel, Standort, Kurzinfo |
| `sensor.bgregal_verliehen` | Anzahl | Liste mit Person und Tagen |
| `sensor.bgregal_neuheiten` | Anzahl neuer Erweiterungen | Liste |
| `sensor.bgregal_letzter_sync` | Zeitpunkt | letzter Fehler |
| `sensor.bgregal_regal_<name>` | Spiele im Regal | Fächer, Spiele; Gerät im Raum des Regals |
| `calendar.bgregal_spieleabende` | nächster Abend | Gäste |
| `button.bgregal_sync` | – | – |

Events: `bgregal_session_started`, `bgregal_session_ended`, `bgregal_loan_overdue`, `bgregal_new_expansion`,
`bgregal_unknown_code`.

## Dienste

Alle Dienste liegen unter `bgregal.*`; ein Spiel gibst du mit `bgg_id` oder `name` an.

| Dienst | Zweck |
| --- | --- |
| `sync_now` | sofort synchronisieren |
| `set_game` | `shelf`, `compartment`, `in_box` (BGG-ID des Kartons, leer = eigener Platz), `in_base` (Kurzform fürs Basisspiel), `nfc_tag`, `ean`, `light_profile`, `playlist`, `manual_url`, `links` (Liste aus `title` und `url`); leer = löschen |
| `scan_code` | gescannter Barcode oder Tag: Sitzung starten/beenden, sonst `unknown` |
| `set_shelf` / `remove_shelf` | Regal: `area_id`, `compartments`, `compartment_1_bottom`, `game_sort`, `new_name` |
| `set_sort_order` | Reihenfolge: `kind` (`rooms`/`shelves`/`games`) und `order` |
| `start_inventory` / `inventory_place` / `inventory_undo` / `inventory_next` / `stop_inventory` | Inventur; `clear_missing` setzt nicht gescannte Spiele des Fachs auf „Ohne Standort“ |
| `assign_scanned_tag` | zuletzt gescannten Tag zuordnen |
| `lend_game` / `return_game` | verleihen (`borrower`) / zurück |
| `start_session` / `end_session` / `cancel_session` | Sitzung; ohne Spiel startet der angenommene Vorschlag |
| `next_player` / `next_round` / `set_order` | Spielhilfe |
| `finish_session` | `players: [{name, score, winner}]`, `note` → Antwort mit `url` und `qr_svg` für BG Stats |
| `session_qr` | Link und QR-Code der abgeschlossenen Sitzung |
| `suggest` / `reject_suggestion` / `accept_suggestion` / `reset_suggestion` | Spielvorschlag |
| `set_player` / `remove_player` | Mitspieler, `bgg_username`, `dislikes`, `hidden` |
| `plan_evening` / `set_candidates` / `vote` / `remove_evening` / `evening_qr` | Spieleabende |
| `dismiss_expansions` | neue Erweiterungen als gesehen markieren |

Beispiel:

```yaml
action: bgregal.set_game
data:
  name: Catan
  shelf: Regal 2
  compartment: 3
  light_profile: scene.spieleabend_gemuetlich
  playlist: https://open.spotify.com/playlist/...
```

## ESP32-Display

Im Ordner `esphome/` liegt die Konfiguration für das Waveshare ESP32-S3 Touch AMOLED 1.75":
`bgregal-display.yaml` (Hauptdatei), `ui.yaml` (Seiten) und `hardware_waveshare_amoled.yaml`.
Das Display zeigt Auswahl → Vorschlag → Standort → Sitzung mit Runde, wer am Zug ist, „Nächster“, „Runde +“ und
„Beenden“. Die Entity-IDs sind fest; nur `secrets.yaml` mit WLAN- und API-Schlüssel anlegen. In Home Assistant beim
Gerät „Aktionen ausführen“ erlauben.

## Daten

Alles liegt in `/config/bgregal.db` (SQLite), Anleitungen unter `/config/bgregal_anleitungen/<BGG-ID>/`. BGG-Daten werden bei jedem Sync überschrieben, deine eigenen Daten nie.
Spielinfos und die Liste der Erweiterungen frischt BGRegal wöchentlich auf, alle Partien einmal pro Woche vollständig
(dabei verschwinden auf BGG gelöschte Partien); dazwischen holt jeder Sync nur neue Partien.

## Entwicklung

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements_test.txt
.venv/Scripts/pytest
```

Der Kern (`custom_components/bgregal/core/`) kommt ohne Home Assistant aus und wird direkt getestet. Panel, Kachel
und Abstimmseite sind reines JavaScript ohne Build-Schritt. Die Übersetzungen (`translations/de.json`, `en.json`)
entstehen aus `scripts/make_translations.py`; Texte dort ändern und das Skript ausführen.

## Lizenz

GPL-3.0
