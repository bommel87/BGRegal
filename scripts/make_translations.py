"""Erzeugt translations/en.json und de.json aus einer Tabelle (gleiche Schlüssel garantiert).

Aufruf aus dem Repo-Ordner:  python scripts/make_translations.py
"""
import json
import sys
from pathlib import Path

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1] / "custom_components" / "bgregal" / "translations"

GAME_FIELDS = {
    "bgg_id": ("BGG ID", "BoardGameGeek ID of the game.", "BGG-ID", "BoardGameGeek-ID des Spiels."),
    "name": ("Name", "Game name (alternative to the BGG ID).", "Name", "Name des Spiels (statt der BGG-ID)."),
}
ORDER = {"order": ("Player order", "Names in turn order.", "Reihenfolge", "Namen in Zugreihenfolge.")}
EVENING = {"evening_id": ("Game night", "ID of the game night.", "Spieleabend", "ID des Spieleabends.")}
BASE = {"base_url": ("Base URL", "Address for the voting link including port, as you open Home Assistant in the browser. Default: the external URL of Home Assistant.",
                     "Basis-Adresse", "Adresse für den Abstimm-Link mit Port, so wie du Home Assistant im Browser öffnest. Standard: die externe URL von Home Assistant.")}
UNITS = {
    "collection": ("games", "Spiele"),
    "plays": ("plays", "Partien"),
    "loans": ("games", "Spiele"),
    "new_expansions": ("expansions", "Erweiterungen"),
    "shelf": ("games", "Spiele"),
}

SERVICES = {
    "sync_now": ("Sync now", "Fetch collection, plays and wishlist from BGG.",
                 "Jetzt synchronisieren", "Sammlung, Partien und Wunschliste von BGG holen.", {}),
    "set_game": ("Set game details", "Location, NFC tag, light and sound profile, manual. Empty value clears it.",
                 "Spiel zuordnen", "Standort, NFC-Tag, Licht- und Soundprofil, Anleitung. Leerer Wert löscht.", {
        **GAME_FIELDS,
        "shelf": ("Shelf", "Name of the shelf.", "Regal", "Name des Regals."),
        "compartment": ("Compartment", "Compartment number from the top (0 = none).", "Fach", "Fachnummer von oben (0 = keins)."),
        "in_base": ("Stored in base game", "Expansion is kept in the base game box.", "Liegt im Basisspiel", "Die Erweiterung liegt in der Schachtel des Basisspiels."),
        "nfc_tag": ("NFC tag", "Tag ID from Settings → Tags.", "NFC-Tag", "Tag-ID aus Einstellungen → Tags."),
        "light_profile": ("Light profile", "Scene or script for the game.", "Lichtprofil", "Szene oder Skript für das Spiel."),
        "playlist": ("Sound profile", "Spotify playlist link or URI.", "Soundprofil", "Spotify-Playlist als Link oder URI."),
        "manual_url": ("Manual", "Link to the rules.", "Anleitung", "Link zur Spielanleitung."),
        "ean": ("EAN", "Barcode on the box (8, 12, 13 or 14 digits).", "EAN", "Barcode auf der Schachtel (8, 12, 13 oder 14 Ziffern)."),
    }),
    "scan_code": ("Scan code", "Barcode (EAN) or tag scanned: starts or ends the session like an NFC tag; unknown codes are reported.",
                  "Code gescannt", "Barcode (EAN) oder Tag gescannt: startet oder beendet die Sitzung wie ein NFC-Tag; unbekannte Codes werden gemeldet.", {
        "code": ("Code", "Scanned EAN or tag ID.", "Code", "Gescannte EAN oder Tag-ID.")}),
    "set_shelf": ("Set shelf", "Room, compartments or a new name for a shelf.",
                  "Regal einstellen", "Raum, Fächer oder neuer Name eines Regals.", {
        "name": ("Shelf", "Current name of the shelf.", "Regal", "Bisheriger Name des Regals."),
        "new_name": ("New name", "Renames the shelf for all games in it.", "Neuer Name", "Benennt das Regal bei allen Spielen darin um."),
        "area_id": ("Room", "Home Assistant area of the shelf (empty = none).", "Raum", "Bereich des Regals in Home Assistant (leer = keiner)."),
        "compartments": ("Compartments", "Number of compartments shown (0 = as used).", "Fächer", "Anzahl der angezeigten Fächer (0 = wie belegt)."),
    }),
    "remove_shelf": ("Remove shelf", "Removes an empty shelf.", "Regal entfernen", "Entfernt ein leeres Regal.", {
        "name": ("Shelf", "Name of the shelf.", "Regal", "Name des Regals.")}),
    "start_inventory": ("Start inventory", "Scan a shelf compartment by compartment; scans set the location instead of starting a session.",
                        "Inventur starten", "Ein Regal Fach für Fach durchscannen; Scans setzen den Standort statt eine Sitzung zu starten.", {
        "shelf": ("Shelf", "Shelf to scan (created if new).", "Regal", "Regal, das durchgescannt wird (wird bei Bedarf angelegt)."),
        "compartment": ("Compartment", "Compartment to start with.", "Fach", "Fach, mit dem es losgeht.")}),
    "inventory_place": ("Place game", "Puts a game into the current compartment of the inventory.",
                        "Spiel einsortieren", "Stellt ein Spiel ins aktuelle Fach der Inventur.", GAME_FIELDS),
    "inventory_undo": ("Undo last scan", "Puts the last scanned game back where it was.",
                       "Letzten Scan zurücknehmen", "Stellt das zuletzt gescannte Spiel an seinen alten Platz zurück.", {}),
    "inventory_next": ("Next compartment", "Continues with the next compartment.",
                       "Nächstes Fach", "Weiter mit dem nächsten Fach.", {
        "clear_missing": ("Clear unscanned", "Games that were in this compartment but not scanned get no location.",
                          "Nicht gescannte leeren", "Spiele, die im Fach standen, aber nicht gescannt wurden, bekommen keinen Standort."),
        "compartment": ("Compartment", "Jump to this compartment instead of the next one.", "Fach", "Zu diesem Fach springen statt zum nächsten.")}),
    "stop_inventory": ("Finish inventory", "Ends the inventory; scans start sessions again.",
                       "Inventur beenden", "Beendet die Inventur; Scans starten wieder Sitzungen.", {
        "clear_missing": ("Clear unscanned", "Games that were in the current compartment but not scanned get no location.",
                          "Nicht gescannte leeren", "Spiele, die im aktuellen Fach standen, aber nicht gescannt wurden, bekommen keinen Standort.")}),
    "assign_scanned_tag": ("Assign scanned tag", "Assign the tag scanned in the last 10 minutes.",
                           "Gescannten Tag zuordnen", "Ordnet den in den letzten 10 Minuten gescannten Tag zu.", GAME_FIELDS),
    "lend_game": ("Lend game", "Mark a game as lent.", "Spiel verleihen", "Markiert ein Spiel als verliehen.", {
        **GAME_FIELDS, "borrower": ("Borrower", "Who has the game.", "An wen", "Wer das Spiel hat.")}),
    "return_game": ("Return game", "The game is back.", "Spiel zurück", "Das Spiel ist zurück.", GAME_FIELDS),
    "start_session": ("Start session", "Starts a game session with light and sound. Without a game: the accepted suggestion.",
                      "Sitzung starten", "Startet eine Spielsitzung mit Licht und Sound. Ohne Spiel: der angenommene Vorschlag.",
                      {**GAME_FIELDS, **ORDER}),
    "end_session": ("End session", "Ends the running session (music pauses, end scene runs).",
                    "Sitzung beenden", "Beendet die laufende Sitzung (Musik pausiert, Szene für Sitzungsende läuft).", {}),
    "cancel_session": ("Discard session", "Discards a running or closes a finished session.",
                       "Sitzung verwerfen", "Verwirft eine laufende oder schließt eine beendete Sitzung.", {}),
    "next_player": ("Next player", "Next player's turn.", "Nächster Spieler", "Der nächste Spieler ist dran.", {}),
    "next_round": ("Next round", "Starts the next round.", "Nächste Runde", "Beginnt die nächste Runde.", {}),
    "set_order": ("Set player order", "Sets the turn order.", "Reihenfolge setzen", "Legt die Zugreihenfolge fest.", ORDER),
    "finish_session": ("Finish session", "Players, scores and winner; returns link and QR code for BG Stats.",
                       "Sitzung abschließen", "Mitspieler, Punkte und Gewinner; liefert Link und QR-Code für BG Stats.", {
        "players": ("Players", "List of players with name, score and winner. Your BGG name stands for you.", "Spieler", "Liste der Spieler mit name, score und winner. Dein BGG-Name steht für dich."),
        "note": ("Note", "Comment for the play.", "Notiz", "Kommentar zur Partie."),
        "auto_winner": ("Automatic winner", "Highest score wins if no winner is set.", "Gewinner automatisch", "Höchste Punktzahl gewinnt, wenn kein Gewinner gesetzt ist."),
    }),
    "session_qr": ("Session QR code", "Link and QR code of the finished session for BG Stats.",
                   "QR-Code der Sitzung", "Link und QR-Code der abgeschlossenen Sitzung für BG Stats.", {}),
    "suggest": ("Suggest a game", "Picks matching games, preferring long-unplayed and well-rated ones.",
                "Spiel vorschlagen", "Wählt passende Spiele, bevorzugt lange nicht gespielte und gut bewertete.", {
        "players": ("Players", "Number of players.", "Spieler", "Anzahl der Spieler."),
        "mode": ("Mode", "Cooperative or competitive.", "Modus", "Kooperativ oder Wettkampf."),
        "game_type": ("Type", "Kind of game.", "Typ", "Art des Spiels."),
        "max_playtime": ("Max. playing time", "In minutes.", "Max. Spieldauer", "In Minuten."),
        "attendees": ("Attendees", "Their dislikes are respected.", "Anwesende", "Deren Vorlieben werden berücksichtigt."),
    }),
    "reject_suggestion": ("Next suggestion", "Rejects the current suggestion.", "Nächster Vorschlag", "Lehnt den aktuellen Vorschlag ab.", {}),
    "accept_suggestion": ("Accept suggestion", "Accepts the suggestion; its location is shown.", "Vorschlag annehmen", "Nimmt den Vorschlag an; der Standort wird angezeigt.", {}),
    "reset_suggestion": ("Reset suggestion", "Back to the start.", "Vorschlag zurücksetzen", "Zurück zum Anfang.", {}),
    "set_player": ("Set player", "Adds or changes a player.", "Mitspieler setzen", "Legt einen Mitspieler an oder ändert ihn.", {
        "name": ("Name", "Name of the player.", "Name", "Name des Mitspielers."),
        "bgg_username": ("BGG user", "BoardGameGeek user name (checked).", "BGG-Benutzer", "BoardGameGeek-Benutzername (wird geprüft)."),
        "dislikes": ("Dislikes", "Kinds of games this player does not like.", "Mag nicht", "Arten von Spielen, die dieser Mitspieler nicht mag."),
        "hidden": ("Hidden", "Hide this player from selection lists; plays and stats stay.",
                   "Ausgeblendet", "Mitspieler in Auswahllisten ausblenden; Partien und Statistik bleiben."),
    }),
    "remove_player": ("Remove player", "Removes a player you added yourself.", "Mitspieler entfernen", "Entfernt einen selbst angelegten Mitspieler.", {
        "name": ("Name", "Name of the player.", "Name", "Name des Mitspielers.")}),
    "plan_evening": ("Plan game night", "Creates a game night with guests, candidates and a voting link.",
                     "Spieleabend planen", "Legt einen Spieleabend mit Gästen, Auswahl und Abstimm-Link an.", {
        "title": ("Title", "Name of the evening.", "Titel", "Name des Abends."),
        "start": ("Start", "Date and time.", "Beginn", "Datum und Uhrzeit."),
        "guests": ("Guests", "Names of the guests.", "Gäste", "Namen der Gäste."),
        "max_playtime": ("Max. playing time", "In minutes.", "Max. Spieldauer", "In Minuten."),
        "candidates": ("Games", "BGG IDs to vote on (empty = automatic).", "Spiele", "BGG-IDs zur Abstimmung (leer = automatisch)."),
        **BASE,
    }),
    "set_candidates": ("Set games of the evening", "Replaces the games to vote on.", "Spiele des Abends setzen", "Ersetzt die Spiele zur Abstimmung.", {
        **EVENING, "candidates": ("Games", "BGG IDs.", "Spiele", "BGG-IDs.")}),
    "remove_evening": ("Remove game night", "Deletes a game night.", "Spieleabend löschen", "Löscht einen Spieleabend.", EVENING),
    "vote": ("Vote", "Votes for games on behalf of a guest.", "Abstimmen", "Stimmt für einen Gast ab.", {
        **EVENING, "voter": ("Voter", "Guest name.", "Wer", "Name des Gastes."),
        "games": ("Games", "BGG IDs the guest wants to play.", "Spiele", "BGG-IDs, die der Gast spielen möchte.")}),
    "evening_qr": ("Voting QR code", "Voting link and QR code for guests.", "Abstimm-QR-Code", "Abstimm-Link und QR-Code für Gäste.", {**EVENING, **BASE}),
    "dismiss_expansions": ("Dismiss new expansions", "Marks all new expansions as seen.", "Neuheiten gesehen", "Markiert alle neuen Erweiterungen als gesehen.", {}),
}

ENTITIES = {
    "sensor": {
        "collection": ("Collection", "Sammlung"),
        "plays": ("Plays", "Partien"),
        "session": ("Session", "Sitzung"),
        "suggestion": ("Suggestion", "Vorschlag"),
        "loans": ("Lent out", "Verliehen"),
        "new_expansions": ("New expansions", "Neuheiten"),
        "last_sync": ("Last sync", "Letzter Sync"),
        "shelf": ("Games", "Spiele"),
    },
    "calendar": {"evenings": ("Game nights", "Spieleabende")},
    "button": {"sync": ("Sync now", "Jetzt synchronisieren")},
}

STATES = {
    "session": {"idle": ("Idle", "Keine"), "running": ("Running", "Läuft"), "finished": ("Finished", "Beendet")},
    "suggestion": {"idle": ("Idle", "Bereit"), "suggested": ("Suggested", "Vorgeschlagen"),
                   "accepted": ("Accepted", "Angenommen"), "none": ("No match", "Kein Treffer")},
}

SELECTORS = {
    "mode": {"any": ("Any", "Egal"), "cooperative": ("Cooperative", "Kooperativ"), "competitive": ("Competitive", "Wettkampf")},
    "game_type": {"any": ("Any", "Egal"), "family": ("Family", "Familie"), "strategy": ("Strategy", "Strategie"),
                  "party": ("Party", "Party"), "abstract": ("Abstract", "Abstrakt"), "thematic": ("Thematic", "Thematisch"),
                  "wargame": ("Wargame", "Kriegsspiel"), "children": ("Children", "Kinder")},
}
SELECTORS["dislike"] = {k: v for k, v in {**SELECTORS["mode"], **SELECTORS["game_type"]}.items() if k != "any"}

CONFIG = {
    "user_title": ("Connect BoardGameGeek", "BoardGameGeek verbinden"),
    "user_desc": ("BGG requires an API token for its XML API. Create one at boardgamegeek.com/applications.",
                  "BGG verlangt für die XML-API einen Token. Du erstellst ihn unter boardgamegeek.com/applications."),
    "username": ("BGG user name", "BGG-Benutzername"),
    "token": ("API token", "API-Token"),
    "invalid_auth": ("BGG rejected the token.", "BGG hat den Token abgelehnt."),
    "user_not_found": ("This BGG user does not exist.", "Diesen BGG-Benutzer gibt es nicht."),
    "cannot_connect": ("Could not reach BGG. Try again later.", "BGG ist nicht erreichbar. Später erneut versuchen."),
    "already_configured": ("BGRegal is already set up.", "BGRegal ist bereits eingerichtet."),
    "single_instance_allowed": ("BGRegal is already set up.", "BGRegal ist bereits eingerichtet."),
}
OPTIONS = {
    "scan_interval_hours": ("Sync interval", "Sync-Intervall", "Hours between two syncs with BGG.", "Stunden zwischen zwei Abgleichen mit BGG."),
    "media_player": ("Default media player", "Standard-Wiedergabegerät", "Plays a game's playlist during the session.", "Spielt während der Sitzung die Playlist des Spiels."),
    "end_scene": ("Scene at session end", "Szene bei Sitzungsende", "Scene or script, e.g. normal light.", "Szene oder Skript, z. B. normales Licht."),
    "loan_reminder_days": ("Loan reminder after", "Verleih-Erinnerung nach", "Days until a reminder about a lent game.", "Tage bis zur Erinnerung an ein verliehenes Spiel."),
    "long_unplayed_months": ("Long unplayed after", "„Lange nicht gespielt“ ab", "Months since the last play.", "Monate seit der letzten Partie."),
    "notify_service": ("Also notify", "Zusätzlich benachrichtigen", "Optional notify service, e.g. your phone.", "Optionaler Benachrichtigungsdienst, z. B. dein Handy."),
}


def build(lang: int) -> dict:
    """lang 0 = en, 1 = de"""
    c = lambda k: CONFIG[k][lang]
    data = {
        "config": {
            "step": {"user": {"title": c("user_title"), "description": c("user_desc"),
                              "data": {"username": c("username"), "token": c("token")}}},
            "error": {k: c(k) for k in ("invalid_auth", "user_not_found", "cannot_connect")},
            "abort": {k: c(k) for k in ("already_configured", "single_instance_allowed")},
        },
        "options": {"step": {"init": {
            "title": "BGRegal",
            "data": {k: v[lang] for k, v in OPTIONS.items()},
            "data_description": {k: v[2 + lang] for k, v in OPTIONS.items()},
        }}},
        "entity": {},
        "selector": {k: {"options": {o: v[lang] for o, v in opts.items()}} for k, opts in SELECTORS.items()},
        "services": {},
    }
    for platform, ents in ENTITIES.items():
        data["entity"][platform] = {}
        for key, names in ents.items():
            entry = {"name": names[lang]}
            if key in STATES:
                entry["state"] = {s: v[lang] for s, v in STATES[key].items()}
            if platform == "sensor" and key in UNITS:
                entry["unit_of_measurement"] = UNITS[key][lang]
            data["entity"][platform][key] = entry
    for key, (en_n, en_d, de_n, de_d, fields) in SERVICES.items():
        svc = {"name": (en_n, de_n)[lang], "description": (en_d, de_d)[lang]}
        if fields:
            svc["fields"] = {f: {"name": v[0 + 2 * lang], "description": v[1 + 2 * lang]} for f, v in fields.items()}
        data["services"][key] = svc
    return data


for lang, code in ((0, "en"), (1, "de")):
    (out / f"{code}.json").write_text(
        json.dumps(build(lang), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
print("ok")
