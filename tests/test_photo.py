"""Regal-Scanner per Foto: KI-Antwort lesen und mit der Sammlung abgleichen."""
import pytest

from core.photo import MATCH_SURE, instructions, match, normalize, parse_answer, similarity

GAMES = [
    {"bgg_id": 13, "name": "Catan", "shelf": "Billy", "compartment": 1, "in_box": None},
    {"bgg_id": 822, "name": "Carcassonne", "shelf": "Kallax", "compartment": 2, "in_box": None},
    {"bgg_id": 9209, "name": "Ticket to Ride", "shelf": "Billy", "compartment": 2, "in_box": None},
    {"bgg_id": 14996, "name": "Ticket to Ride: Europe", "shelf": "", "compartment": None, "in_box": None},
    {"bgg_id": 325, "name": "Catan: Seafarers", "shelf": "Billy", "compartment": 1, "in_box": 13},
    {"bgg_id": 30549, "name": "Pandemic", "shelf": "Billy", "compartment": 3, "in_box": None},
]


def test_instructions_name_shelf_and_collection():
    text = instructions({"name": "Billy", "compartments": 4, "reversed": True}, ["Catan", "Pandemic"], 1)
    assert "„Billy“ hat 4 Fächer" in text and "Fach 1 ist das unterste" in text
    assert text.endswith("Catan\nPandemic")
    assert "2 Fotos" in instructions({"name": "B", "compartments": 1}, [], 2)


def test_parse_answer_text_with_fence():
    raw = 'Hier:\n```json\n{"compartments": [{"compartment": 2, "games": [{"title": "Catan", "confidence": 0.9}]},' \
          ' {"compartment": 1, "games": ["Pandemic", {"title": " "}, {"title": "X", "confidence": "?"}]},' \
          ' {"compartment": 9, "games": [{"title": "zu tief"}]}]}\n```'
    assert parse_answer(raw, 3) == [
        {"compartment": 1, "title": "Pandemic", "confidence": 1.0},
        {"compartment": 1, "title": "X", "confidence": 1.0},
        {"compartment": 2, "title": "Catan", "confidence": 0.9},
    ]


def test_parse_answer_compact():
    raw = '{"2":["Catan","Azul?"],"1":["Pandemic"],"7":["zu tief"],"x":["kein Fach"]}'
    assert parse_answer(raw, 3) == [
        {"compartment": 1, "title": "Pandemic", "confidence": 1.0},
        {"compartment": 2, "title": "Catan", "confidence": 1.0},
        {"compartment": 2, "title": "Azul", "confidence": 0.4},
    ]


@pytest.mark.parametrize("raw", ["kein json", "[1, 2]", '{"games": []}', "{kaputt}"])
def test_parse_answer_rejects(raw):
    with pytest.raises(ValueError):
        parse_answer(raw, 3)


def test_similarity():
    assert normalize("Die Siedler von Catan!") == "siedler von catan"
    assert similarity("CATAN", "Catan") == 1.0
    assert similarity("Carcassonne: Das Spiel", "Carcassonne") >= MATCH_SURE
    assert similarity("Carcasonne", "Carcassonne") >= MATCH_SURE  # ein Buchstabe falsch gelesen
    assert similarity("Azul", "Pandemic") < 0.6


def test_match_groups():
    found = [
        {"compartment": 1, "title": "Catan", "confidence": 0.95},  # steht schon hier
        {"compartment": 1, "title": "Carcassonne", "confidence": 0.9},  # laut BGRegal im Kallax
        {"compartment": 2, "title": "Ticket to Ride", "confidence": 0.4},  # KI unsicher
        {"compartment": 2, "title": "Azul", "confidence": 0.9},  # nicht in der Sammlung
        {"compartment": 3, "title": "Catan", "confidence": 0.9},  # doppelt -> nicht noch einmal sicher
    ]
    result = match(found, GAMES, "billy")
    status = [(i["title"], i["status"], i["bgg_id"]) for i in result["items"]]
    assert status == [
        ("Catan", "ok", 13),
        ("Carcassonne", "moved", 822),
        ("Ticket to Ride", "unsure", 9209),
        ("Azul", "unknown", None),
        ("Catan", "unknown", None),
    ]
    assert result["items"][1]["from"] == "Kallax, 2"
    assert result["items"][2]["candidates"][0] == {"bgg_id": 9209, "name": "Ticket to Ride"}
    # Seafarers liegt im Catan-Karton und fehlt deshalb nicht; Ticket to Ride ist noch unentschieden
    assert [m["name"] for m in result["missing"]] == ["Ticket to Ride", "Pandemic"]


def test_match_close_candidates_ask():
    found = [{"compartment": 1, "title": "Ticket to Ride Europe", "confidence": 0.9}]
    item = match(found, GAMES, "Billy")["items"][0]
    assert item["bgg_id"] == 14996
    assert item["status"] == "moved" and item["from"] == ""  # bisher ohne Standort
