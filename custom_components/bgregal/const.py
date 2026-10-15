"""Konstanten für BGRegal."""
from __future__ import annotations

DOMAIN = "bgregal"
VERSION = "0.2.0"

CONF_USERNAME = "username"
CONF_TOKEN = "token"

CONF_SCAN_HOURS = "scan_interval_hours"
CONF_MEDIA_PLAYER = "media_player"
CONF_END_SCENE = "end_scene"
CONF_LOAN_DAYS = "loan_reminder_days"
CONF_LONG_MONTHS = "long_unplayed_months"
CONF_NOTIFY = "notify_service"

DEFAULTS = {
    CONF_SCAN_HOURS: 6,
    CONF_MEDIA_PLAYER: "",
    CONF_END_SCENE: "",
    CONF_LOAN_DAYS: 60,
    CONF_LONG_MONTHS: 24,
    CONF_NOTIFY: "",
}

DB_FILE = "bgregal.db"
STATIC_URL = "/bgregal_static"
PANEL_URL = "bgregal"
SIGNAL_UPDATE = "bgregal_update"

EVENT_SESSION_STARTED = "bgregal_session_started"
EVENT_SESSION_ENDED = "bgregal_session_ended"
EVENT_LOAN_OVERDUE = "bgregal_loan_overdue"
EVENT_NEW_EXPANSION = "bgregal_new_expansion"
EVENT_UNKNOWN_CODE = "bgregal_unknown_code"

TAG_MAX_AGE_MIN = 10  # gescannter Tag gilt so lange für „Gescannten übernehmen“
LOAN_REPEAT_DAYS = 30  # nach der ersten Erinnerung alle 30 Tage erneut
EVENING_CANDIDATES = 8
