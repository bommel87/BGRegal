# BGRegal

*English version: [README.en.md](README.en.md)*

BGRegal bringt deine BoardGameGeek-Sammlung nach Home Assistant und steuert den Spieleabend: virtuelles Regal,
NFC-Tag je Spiel, Licht- und Soundprofil, Spielhilfe während der Partie, Übergabe an BG Stats, Spielvorschlag,
Spieleabend-Planung mit Abstimmung, Statistik, Pile of Shame, Wunschliste und Verleih.

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
| **Regal** | Spiele nach Regal und Fach, Suche, Filter. Jede Schachtel zeigt Partienzahl und letzte Partie. |
| **Spiel-Fenster** | Infos, letzte Partien, Erweiterungen; Standort, NFC-Tag, Licht, Sound, Anleitung; verleihen; Sitzung starten |
| **Sitzung** | Laufzeit, Runde, wer am Zug ist; danach Mitspieler, Punkte, Gewinner und QR-Code für BG Stats |
| **Vorschlag** | Filter nach Spielerzahl, Modus, Typ, Dauer und Anwesenden; Ja/Nein; Standort |
| **Spieleabende** | Termin, Gäste, Spiele zur Wahl, Abstimm-Link und QR-Code, Rangliste |
| **Mitspieler** | aus deinen BGG-Partien plus selbst angelegte, mit BGG-Name und Vorlieben; ausblendbar |
| **Statistik** | Partien pro Monat, meistgespielt, lange nicht gespielt, H-Index |
| **Pile of Shame** | alle eigenen Spiele ohne eine einzige Partie |
| **Wunschliste** | Wunschliste von BGG und neue Erweiterungen zu deinen Spielen |
| **Verliehen** | was an wen seit wann verliehen ist |

### Standort

Regal und Fach trägst du im Spiel-Fenster ein. Fach 1 ist das oberste. Eine Erweiterung kann „im Basisspiel“ liegen;
dann steht sie nicht extra im Regal, sondern zählt beim Basisspiel mit.

### NFC

Tag an die Schachtel kleben, mit der Home-Assistant-App scannen und im Spiel-Fenster **Gescannten übernehmen**
drücken (gilt für den Tag der letzten 10 Minuten). Danach gilt:

- **Scan** startet die Sitzung: Lichtprofil (Szene oder Skript) und Playlist laufen an.
- **Zweiter Scan** desselben Tags beendet sie: Musik pausiert, die Szene für Sitzungsende läuft.

### Spieleabend und Abstimmung

Beim Anlegen wählt BGRegal bis zu acht passende Spiele für die Zahl der Gäste aus und berücksichtigt deren
Vorlieben. Die Auswahl kannst du ändern. Jeder Abend bekommt einen geheimen Link mit QR-Code auf eine kleine
Abstimmseite. Gäste brauchen **kein** Home-Assistant-Konto; wer den Link hat, kann nur für diesen Abend abstimmen.
Im WLAN funktioniert der Link immer, von unterwegs nur, wenn Home Assistant von außen erreichbar ist
(z. B. über Nabu Casa). Abstimmen geht bis 6 Uhr am Morgen nach dem Abend.

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
| `calendar.bgregal_spieleabende` | nächster Abend | Gäste |
| `button.bgregal_sync` | – | – |

Events: `bgregal_session_started`, `bgregal_session_ended`, `bgregal_loan_overdue`, `bgregal_new_expansion`.

## Dienste

Alle Dienste liegen unter `bgregal.*`; ein Spiel gibst du mit `bgg_id` oder `name` an.

| Dienst | Zweck |
| --- | --- |
| `sync_now` | sofort synchronisieren |
| `set_game` | `shelf`, `compartment`, `in_base`, `nfc_tag`, `light_profile`, `playlist`, `manual_url`; leer = löschen |
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

Alles liegt in `/config/bgregal.db` (SQLite). BGG-Daten werden bei jedem Sync überschrieben, deine eigenen Daten nie.
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
