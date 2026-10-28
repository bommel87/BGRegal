# BGRegal

*Deutsche Version: [README.md](README.md)*

BGRegal brings your BoardGameGeek collection into Home Assistant and runs your game night: a virtual shelf, an NFC
tag per game, light and sound profiles, a play helper during the game, hand-off to BG Stats, game suggestions, game
night planning with voting, stats, pile of shame, wishlist, loans and rules questions in HA Assist.

**BGG is the source, BG Stats is where plays live.** BGRegal only reads from BGG and never writes to it. At the end of
a game you hand the play to BG Stats with a QR code; BG Stats syncs it to BGG and it shows up in BGRegal after the
next sync. BGRegal stores locally only what BGG doesn't know: location, NFC tag, profiles, loans, player dislikes and
game nights.

## Installation

1. HACS → *Custom repositories* → `https://github.com/bommel87/BGRegal`, category *Integration*.
   Without HACS: copy `custom_components/bgregal` to `/config/custom_components/`.
2. Restart Home Assistant.
3. *Settings → Devices & services → Add integration → BGRegal*. BGG requires an **API token** for its XML API;
   create one at [boardgamegeek.com/applications](https://boardgamegeek.com/applications).
4. **BGRegal** appears in the sidebar. The first sync loads the collection, game info and all plays and can take a
   few minutes.

### Options

| Option | Default | Purpose |
| --- | --- | --- |
| Sync interval | 6 h | time between two syncs with BGG |
| Default media player | – | plays a game's playlist during the session |
| Scene at session end | – | e.g. back to normal light |
| Loan reminder after | 60 days | then again every 30 days |
| Long unplayed after | 24 months | for stats and suggestions |
| Also notify | – | e.g. `notify.mobile_app_phone`; otherwise only a HA notification |

## The panel

Shelf (by shelf and compartment, with plays and last play on every box), game dialog (info, recent plays,
expansions, location, NFC tag, light, sound, rules link and rulebook PDFs, lending, start), session (timer, round, whose turn; afterwards
players, scores, winner and a QR code for BG Stats), suggestions, game nights (guests, games, voting link and QR
code, ranking), players (with BGG user and dislikes), stats, pile of shame, wishlist with new expansions, and loans.

**Boxes:** an expansion can be stored in any box of your collection, not only its base game (*Stored in box of*).
It then takes the box's location, the box tile shows the count, and searching for the expansion highlights the box.

**NFC:** stick a tag on the box, scan it with the Home Assistant app and press **Use scanned tag** in the game
dialog. Afterwards a scan starts the session (light profile and playlist), a second scan of the same tag ends it.

**Voting:** every game night gets a secret link with a QR code to a small voting page. Guests need **no** Home
Assistant account; the link only allows voting for that evening. It always works on your Wi-Fi, from outside only if
Home Assistant is reachable externally. Voting closes at 6 am the morning after.

**Rules questions:** upload rulebooks in the game dialog under **Rulebooks (PDF)**, several per game if needed. Give
your Assist agent an LLM (e.g. the Anthropic integration with your own API key) and tick **Spielregeln (BGRegal)**
under *Configure → Control Home Assistant*. Then ask Assist, e.g. "Can the robber go on the desert in Catan?". Without
a game name it means the game of the running session. The LLM only answers from the rulebook, cites the page and
says when the rulebook doesn't cover it. Scanned PDFs without a text layer can't be read; max. 100 MB per file.
Below the PDFs you can add any number of **links** (errata, FAQ, almanac). Assist reads the pages or PDFs behind them
too, errata first; the text is cached for 7 days. Pages behind a login or rendered by JavaScript often yield no text.

## Dashboard card

```yaml
type: custom:bgregal-card
bgg_id: 13      # optional; without: the game of the running session, otherwise the current suggestion
```

## Entities, events and services

Entities: `sensor.bgregal_sammlung` (collection), `sensor.bgregal_partien` (plays), `sensor.bgregal_sitzung`
(session: `idle`/`running`/`finished`), `sensor.bgregal_vorschlag` (suggestion), `sensor.bgregal_verliehen` (loans),
`sensor.bgregal_neuheiten` (new expansions), `sensor.bgregal_letzter_sync`, `calendar.bgregal_spieleabende`,
`button.bgregal_sync`. The entity IDs are fixed so automations and the ESP32 display work in any language.

Events: `bgregal_session_started`, `bgregal_session_ended`, `bgregal_loan_overdue`, `bgregal_new_expansion`.

Services (`bgregal.*`): `sync_now`, `set_game`, `assign_scanned_tag`, `lend_game`, `return_game`, `start_session`,
`end_session`, `cancel_session`, `next_player`, `next_round`, `set_order`, `finish_session`, `session_qr`,
`suggest`, `reject_suggestion`, `accept_suggestion`, `reset_suggestion`, `set_player`, `remove_player`,
`plan_evening`, `set_candidates`, `vote`, `remove_evening`, `evening_qr`, `dismiss_expansions`.

## ESP32 display

`esphome/` contains the configuration for the Waveshare ESP32-S3 Touch AMOLED 1.75": selection → suggestion →
location → session with round, whose turn, "next", "round +" and "end". Only add a `secrets.yaml`.

## Data

Everything lives in `/config/bgregal.db` (SQLite), rulebooks in `/config/bgregal_anleitungen/<BGG id>/`. BGG data is overwritten on every sync, your own data never.

## License

GPL-3.0
