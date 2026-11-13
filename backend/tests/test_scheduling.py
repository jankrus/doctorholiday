"""Availability arithmetic (BR-23) without a database."""

from datetime import UTC, datetime, time, timedelta

import pytest

from doctorholiday.scheduling import (
    PRACTICE_TIME_ZONE,
    Blocked,
    Interval,
    available_times,
    is_offered,
    start_times,
)

BERLIN = PRACTICE_TIME_ZONE
# Monday, 7 January 2030 (winter time, UTC+1).
MONDAY = datetime(2030, 1, 7, tzinfo=BERLIN)
# Shortly before every time used here, so none is in the past or more than 365 days ahead.
LONG_AGO = datetime(2030, 1, 1, tzinfo=UTC)
NOTHING = Blocked([])


def local(day: datetime, hour: int, minute: int = 0) -> datetime:
    return day.replace(hour=hour, minute=minute)


def times(
    *entries: tuple[int, time, time], blocked: Blocked = NOTHING, **kwargs: object
) -> list[datetime]:
    options: dict[str, object] = {
        "starts_from": MONDAY,
        "starts_before": MONDAY + timedelta(days=1),
        "minutes": 15,
        "now": LONG_AGO,
    }
    options.update(kwargs)
    return available_times(entries, blocked, **options)  # type: ignore[arg-type]


def test_several_entries_per_day_are_cut_into_steps_and_a_short_remainder_is_dropped() -> None:
    found = times((1, time(8), time(8, 40)), (1, time(14), time(14, 30)), (2, time(8), time(9)))

    assert found == [
        local(MONDAY, 8),
        local(MONDAY, 8, 15),
        # 08:30-08:45 would end after 08:40
        local(MONDAY, 14),
        local(MONDAY, 14, 15),
    ]
    assert all(moment.tzinfo is UTC for moment in found)
    assert found[0] == datetime(2030, 1, 7, 7, 0, tzinfo=UTC)


def test_the_appointment_length_sets_the_step() -> None:
    found = times((1, time(8), time(9)), minutes=25)

    assert found == [local(MONDAY, 8), local(MONDAY, 8, 25)]


def test_absences_and_bookings_remove_every_overlapping_start() -> None:
    blocked = Blocked(
        [
            # absence 08:20-08:50: blocks 08:15, 08:30 and 08:45
            Interval(local(MONDAY, 8, 20), local(MONDAY, 8, 50)),
            # booked 09:30-09:45
            Interval(local(MONDAY, 9, 30), local(MONDAY, 9, 45)),
        ]
    )

    found = times((1, time(8), time(10)), blocked=blocked)

    assert found == [local(MONDAY, 8), local(MONDAY, 9), local(MONDAY, 9, 15), local(MONDAY, 9, 45)]


def test_overlapping_and_touching_blocks_are_merged() -> None:
    blocked = Blocked(
        [
            Interval(local(MONDAY, 8), local(MONDAY, 8, 30)),
            Interval(local(MONDAY, 8, 10), local(MONDAY, 8, 20)),
            Interval(local(MONDAY, 8, 30), local(MONDAY, 8, 45)),
        ]
    )

    assert times((1, time(8), time(9)), blocked=blocked) == [local(MONDAY, 8, 45)]


def test_only_future_times_at_most_365_days_ahead() -> None:
    entry = (1, time(8), time(9))
    now = local(MONDAY, 8, 15)

    assert times(entry, now=now) == [local(MONDAY, 8, 30), local(MONDAY, 8, 45)]
    far = times(entry, now=local(MONDAY, 8, 30) - timedelta(days=365))
    assert far == [local(MONDAY, 8), local(MONDAY, 8, 15), local(MONDAY, 8, 30)]


def test_the_range_bounds_the_start_inclusive_and_exclusive() -> None:
    found = times(
        (1, time(8), time(10)),
        starts_from=local(MONDAY, 8, 15),
        starts_before=local(MONDAY, 9, 15),
    )

    assert found == [
        local(MONDAY, 8, 15),
        local(MONDAY, 8, 30),
        local(MONDAY, 8, 45),
        local(MONDAY, 9),
    ]


def test_a_range_in_utc_covers_the_local_dates_it_touches() -> None:
    # 23:30 UTC on Sunday is already Monday 00:30 in Berlin.
    found = times(
        (1, time(0, 30), time(1)),
        starts_from=datetime(2030, 1, 6, 23, 0, tzinfo=UTC),
        starts_before=datetime(2030, 1, 7, 0, 0, tzinfo=UTC),
    )

    assert found == [
        datetime(2030, 1, 6, 23, 30, tzinfo=UTC),
        datetime(2030, 1, 6, 23, 45, tzinfo=UTC),
    ]


@pytest.mark.parametrize(
    ("before", "after", "offsets"),
    [
        # Summer time starts on Sunday, 31 March 2030: 08:00 is 07:00 UTC before, 06:00 after.
        (datetime(2030, 3, 25, tzinfo=BERLIN), datetime(2030, 4, 1, tzinfo=BERLIN), (7, 6)),
        # Winter time starts on Sunday, 27 October 2030: 08:00 is 06:00 UTC before, 07:00 after.
        (datetime(2030, 10, 21, tzinfo=BERLIN), datetime(2030, 10, 28, tzinfo=BERLIN), (6, 7)),
    ],
)
def test_daylight_saving_changes_keep_the_local_time(
    before: datetime, after: datetime, offsets: tuple[int, int]
) -> None:
    found = times(
        (1, time(8), time(8, 15)),
        starts_from=before,
        starts_before=after + timedelta(days=1),
    )

    assert [moment.astimezone(BERLIN).strftime("%a %d %H:%M") for moment in found] == [
        before.strftime("%a %d 08:00"),
        after.strftime("%a %d 08:00"),
    ]
    assert [moment.hour for moment in found] == list(offsets)


def test_the_night_of_a_change_counts_real_time() -> None:
    sunday = datetime(2030, 3, 31, tzinfo=BERLIN)  # 02:00-03:00 does not exist
    found = list(
        start_times(
            [(7, time(1), time(4))],
            starts_from=sunday,
            starts_before=sunday + timedelta(days=1),
            minutes=60,
        )
    )

    # 01:00-04:00 local lasts two real hours on this night.
    assert [moment.astimezone(BERLIN).hour for moment in found] == [1, 3]


def test_is_offered_checks_steps_absences_and_the_window() -> None:
    entries = [(1, time(8), time(10))]
    absence = [Interval(local(MONDAY, 9), local(MONDAY, 9, 30))]

    def offered(starts_at: datetime, now: datetime = LONG_AGO) -> bool:
        return is_offered(entries, absence, starts_at=starts_at, minutes=15, now=now)

    assert offered(local(MONDAY, 8, 45))
    assert not offered(local(MONDAY, 8, 50))  # not a step
    assert not offered(local(MONDAY, 9, 15))  # absent
    assert not offered(local(MONDAY, 10))  # outside the hours
    assert not offered(local(MONDAY, 8), now=local(MONDAY, 8))  # not in the future
    assert not offered(local(MONDAY, 8), now=local(MONDAY, 8) - timedelta(days=366))
    assert not offered(local(MONDAY, 8) + timedelta(days=1))  # Tuesday
