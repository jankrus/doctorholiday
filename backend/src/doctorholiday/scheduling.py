"""Available appointment times, computed from working hours, absences and bookings (BR-23).

Nothing here touches the database: the API loads the rows, these functions do the arithmetic,
so the rules are tested without a database (tests/test_scheduling.py).

- Working hours are local wall-clock times in the practice time zone (`Europe/Berlin`, BR-08).
  They are converted to UTC **per date**, so an entry "Monday 08:00-12:00" is 07:00-11:00 UTC in
  winter and 06:00-10:00 UTC in summer, and the week of a daylight-saving change is right too.
- Each entry is cut into consecutive start times of `appointmentMinutes` from its start; a
  remainder shorter than one appointment is dropped. The steps are counted in real (UTC) time,
  so on the night of a change an entry spanning 02:00-03:00 yields as many times as it really
  lasts. A local start time that does not exist (spring forward) is read with the offset before
  the change (`fold=0`), as `zoneinfo` does.
- A start time is available if it lies in the future, at most 365 days ahead, and the appointment
  would overlap neither an absence nor a booked appointment.
"""

import bisect
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

PRACTICE_TIME_ZONE = ZoneInfo("Europe/Berlin")
MAX_DAYS_AHEAD = timedelta(days=365)
MAX_RANGE = timedelta(days=31)

# (ISO weekday 1-7, start, end) in local time, as stored in `working_hours`.
WorkingHoursEntry = tuple[int, time, time]


@dataclass(frozen=True, order=True)
class Interval:
    """A half-open time range [starts_at, ends_at) with time-zone aware ends."""

    starts_at: datetime
    ends_at: datetime


def start_times(
    entries: Iterable[WorkingHoursEntry],
    *,
    starts_from: datetime,
    starts_before: datetime,
    minutes: int,
) -> Iterator[datetime]:
    """Start times (UTC) the working hours offer in [starts_from, starts_before), ascending.

    Only the cut into steps; absences, bookings and "in the future" are not considered.
    """
    by_weekday: dict[int, list[tuple[time, time]]] = {}
    for weekday, start, end in entries:
        by_weekday.setdefault(weekday, []).append((start, end))
    for day_entries in by_weekday.values():
        day_entries.sort()
    length = timedelta(minutes=minutes)

    day = starts_from.astimezone(PRACTICE_TIME_ZONE).date()
    last_day = starts_before.astimezone(PRACTICE_TIME_ZONE).date()
    while day <= last_day:
        for start, end in by_weekday.get(day.isoweekday(), ()):
            # Local wall time of this date to UTC: the offset of this very date.
            moment = datetime.combine(day, start, tzinfo=PRACTICE_TIME_ZONE).astimezone(UTC)
            finish = datetime.combine(day, end, tzinfo=PRACTICE_TIME_ZONE).astimezone(UTC)
            while moment + length <= finish:
                if starts_from <= moment < starts_before:
                    yield moment
                moment += length
        day += timedelta(days=1)


class Blocked:
    """Absences and booked appointments of one doctor, for fast overlap checks."""

    def __init__(self, intervals: Iterable[Interval]) -> None:
        # Merged into disjoint, sorted intervals, so one binary search answers each check.
        merged: list[Interval] = []
        for interval in sorted(intervals):
            if merged and interval.starts_at <= merged[-1].ends_at:
                last = merged[-1]
                merged[-1] = Interval(last.starts_at, max(last.ends_at, interval.ends_at))
            else:
                merged.append(interval)
        self._starts = [interval.starts_at for interval in merged]
        self._ends = [interval.ends_at for interval in merged]

    def overlaps(self, starts_at: datetime, ends_at: datetime) -> bool:
        # The first blocked interval that ends after starts_at is the only candidate.
        index = bisect.bisect_right(self._ends, starts_at)
        return index < len(self._starts) and self._starts[index] < ends_at


def _bookable_moment(starts_at: datetime, now: datetime) -> bool:
    return now < starts_at <= now + MAX_DAYS_AHEAD


def available_times(
    entries: Iterable[WorkingHoursEntry],
    blocked: Blocked,
    *,
    starts_from: datetime,
    starts_before: datetime,
    minutes: int,
    now: datetime,
) -> list[datetime]:
    """Available start times (UTC) of one doctor in [starts_from, starts_before), ascending."""
    length = timedelta(minutes=minutes)
    return [
        moment
        for moment in start_times(
            entries, starts_from=starts_from, starts_before=starts_before, minutes=minutes
        )
        if _bookable_moment(moment, now) and not blocked.overlaps(moment, moment + length)
    ]


def is_offered(
    entries: Iterable[WorkingHoursEntry],
    absences: Sequence[Interval],
    *,
    starts_at: datetime,
    minutes: int,
    now: datetime,
) -> bool:
    """Whether `starts_at` is a start time the doctor offers (BR-09, BR-22): one of the steps of
    the working hours, in the future, at most 365 days ahead and outside every absence.

    Booked appointments are left to the database: the exclusion constraint rejects an overlap
    with `409 TIME_ALREADY_BOOKED`, for concurrent bookings too, so a time taken by someone else
    is reported as taken, not as never offered.
    """
    if not _bookable_moment(starts_at, now):
        return False
    offered = start_times(
        entries,
        starts_from=starts_at,
        starts_before=starts_at + timedelta(microseconds=1),
        minutes=minutes,
    )
    if next(offered, None) != starts_at:
        return False
    return not Blocked(absences).overlaps(starts_at, starts_at + timedelta(minutes=minutes))
