import json
import random
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from core import session as sess
from core.bgstats import auto_winners, play_url, qr_svg
from core.stats import h_index, long_unplayed, overview, pile_of_shame, plays_per_month
from core.suggest import disliked, matches, rank, weight
from core.util import normalize_playlist, valid_light_profile

TODAY = date(2026, 10, 14)

COOP = {"bgg_id": 1, "name": "Pandemic", "min_players": 2, "max_players": 4, "playing_time": 45,
        "mode": "cooperative", "game_types": ["thematic"], "plays": 5, "last_play": "2026-10-01"}
COMP = {"bgg_id": 2, "name": "Catan", "min_players": 3, "max_players": 4, "playing_time": 120,
        "mode": "competitive", "game_types": ["family"], "plays": 0, "last_play": None}
EXP = {"bgg_id": 3, "name": "Erw.", "expansion": True, "min_players": 2, "max_players": 4}


def test_matches_filters():
    assert matches(COOP, players=2, mode="cooperative", max_playtime=60)
    assert not matches(COOP, players=5)
    assert not matches(COMP, mode="cooperative")
    assert not matches(COMP, max_playtime=60)
    assert not matches(EXP)
    assert not matches({**COOP, "loan": {"borrower": "Ben"}})  # verliehen
    assert matches({**COOP, "mode": "semi"}, mode="competitive")


def test_dislikes():
    assert disliked(COOP, {"cooperative"}) and disliked(COMP, {"family"})
    assert not disliked(COMP, {"cooperative"})


def test_weight_prefers_never_and_long_unplayed():
    recent = weight({**COOP, "last_play": "2026-10-13"}, TODAY)
    old = weight({**COOP, "last_play": "2023-10-01"}, TODAY)
    assert weight(COMP, TODAY) > recent and old > recent


def test_rank_excludes_and_is_deterministic():
    games = [COOP, COMP, EXP]
    a = rank(games, TODAY, random.Random(1))
    b = rank(games, TODAY, random.Random(1))
    assert [g["bgg_id"] for g in a] == [g["bgg_id"] for g in b]
    assert {g["bgg_id"] for g in a} == {1, 2}
    assert [g["bgg_id"] for g in rank(games, TODAY, random.Random(1), dislikes={"cooperative"})] == [2]


def test_stats():
    rows = [{"date": "2026-10-10", "quantity": 1}, {"date": "2026-09-01", "quantity": 2},
            {"date": "2024-01-01", "quantity": 1}]
    months = plays_per_month(rows, TODAY)
    assert len(months) == 12 and months[-1] == {"month": "2026-10", "plays": 1}
    assert months[-2] == {"month": "2026-09", "plays": 2} and months[0]["month"] == "2025-11"
    assert h_index([10, 8, 5, 4, 3]) == 4 and h_index([]) == 0 and h_index([0]) == 0
    assert [g["bgg_id"] for g in pile_of_shame([COOP, COMP, EXP])] == [2]
    old = {**COOP, "bgg_id": 9, "last_play": "2024-09-30"}
    assert [g["bgg_id"] for g in long_unplayed([COOP, old], TODAY, 24)] == [9]
    o = overview([COOP, COMP, EXP], rows, TODAY, 24)
    assert o["games"] == 2 and o["expansions"] == 1 and o["plays_total"] == 4
    assert o["plays_this_month"] == 1 and o["pile_of_shame"] == [2] and o["top"] == [1]


def test_bgstats_url():
    players = [{"name": "Susi", "username": "susi", "score": "10", "winner": True},
               {"name": "Anna", "score": "8,5"}]
    ended = datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)
    url = play_url("susi", "Catan", 13, ended, 95, players, note="Knapp")
    data = json.loads(parse_qs(urlparse(url).query)["data"][0])
    assert data["game"]["bggId"] == 13 and data["durationMin"] == 95 and data["comments"] == "Knapp"
    assert data["playDate"] == "2026-10-14 21:00:00"
    assert data["players"][0] == {"name": "Susi", "sourcePlayerId": "bgg:susi", "winner": True, "score": 10.0}
    assert data["players"][1]["sourcePlayerId"] == "name:anna" and data["players"][1]["score"] == 8.5
    assert not data["game"]["noPoints"]
    assert auto_winners(players) == {"susi"}
    assert auto_winners([{"name": "A", "score": "3"}, {"name": "B", "score": "3"}]) == {"a", "b"}
    assert auto_winners([{"name": "A"}]) == set()
    assert qr_svg(url).startswith("<svg")


def test_session_flow():
    start = datetime(2026, 10, 14, 19, 0, tzinfo=timezone.utc)
    s = sess.start(13, "Catan", start, ["Anna", "Susi"])
    assert sess.current_player(s) == "Anna" and s["round"] == 1
    s = sess.next_player(s)
    assert sess.current_player(s) == "Susi" and s["round"] == 1
    s = sess.next_player(s)
    assert sess.current_player(s) == "Anna" and s["round"] == 2
    s = sess.next_round(sess.next_player(s))
    assert s["round"] == 3 and s["turn"] == 0
    s = sess.end(s, start + timedelta(minutes=94, seconds=40))
    assert s["state"] == sess.FINISHED and sess.duration_min(s) == 95
    empty = sess.next_player(sess.start(1, "x", start))
    assert empty["round"] == 2 and sess.current_player(empty) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("https://open.spotify.com/playlist/37i9dQZF1DX?si=1", "spotify:playlist:37i9dQZF1DX"),
     ("https://open.spotify.com/intl-de/album/abc", "spotify:album:abc"),
     ("spotify:playlist:xyz", "spotify:playlist:xyz"), ("  ", "")],
)
def test_playlist(raw, expected):
    assert normalize_playlist(raw) == expected


def test_playlist_and_profile_invalid():
    with pytest.raises(ValueError):
        normalize_playlist("https://example.com")
    assert valid_light_profile("scene.spieleabend") and valid_light_profile("")
    assert not valid_light_profile("light.wohnzimmer")
