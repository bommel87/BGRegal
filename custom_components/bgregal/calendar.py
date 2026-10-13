"""Spieleabende als Kalender."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import BgRegalEntity

EVENING_HOURS = 4  # angenommene Dauer eines Abends


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([BgRegalCalendar(entry.runtime_data)])


class BgRegalCalendar(BgRegalEntity, CalendarEntity):
    _attr_icon = "mdi:calendar-star"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "evenings", "calendar", "spieleabende")

    def _events(self) -> list[CalendarEvent]:
        events = []
        for e in self.snapshot.get("evenings", []):
            start = dt_util.parse_datetime(e["start"])
            if start is None:
                continue
            if start.tzinfo is None:
                start = start.replace(tzinfo=dt_util.get_default_time_zone())
            guests = ", ".join(e["guests"])
            events.append(
                CalendarEvent(
                    start=start,
                    end=start + timedelta(hours=EVENING_HOURS),
                    summary=e["title"],
                    description=guests or None,
                    uid=f"bgregal-evening-{e['id']}",
                )
            )
        return events

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        upcoming = [ev for ev in self._events() if ev.end > now]
        return min(upcoming, key=lambda ev: ev.start, default=None)

    @property
    def extra_state_attributes(self):
        ev = self.event
        if ev is None:
            return {}
        return {"guests": ev.description or ""}

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [ev for ev in self._events() if ev.end > start_date and ev.start < end_date]
