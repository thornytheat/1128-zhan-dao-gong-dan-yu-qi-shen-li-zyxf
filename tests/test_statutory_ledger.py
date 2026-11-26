from dataclasses import replace
from types import SimpleNamespace

import pytest

from permitdesk.calendar_intervals.business_time import balance
from permitdesk.calendar_intervals.clock_receipt import office_projection
from permitdesk.calendar_intervals.service import clock_records


def projected(opened, snapshot, limit, office=(), paused=()):
    account = balance('T-101', opened, snapshot, limit, office, paused)
    return office_projection(account, opened, snapshot, office, paused)


def test_interleaved_closures_charge_only_open_minutes():
    ledger = projected(90, 230, 105, [(100, 160), (175, 260)], [(120, 130), (155, 183)])
    assert [(row['start_minute'], row['end_minute'], row['state']) for row in ledger['timeline']] == [
        (90, 100, '窗口停办'), (100, 120, '计入时限'), (120, 130, '补正暂停'),
        (130, 155, '计入时限'), (155, 160, '补正暂停'), (160, 175, '窗口停办'),
        (175, 183, '补正暂停'), (183, 230, '计入时限'),
    ]
    assert ledger['elapsed_wall_minutes'] == 140
    assert ledger['charged_minutes'] == 92
    assert ledger['closed_minutes'] == 25
    assert ledger['paused_in_office_minutes'] == 23
    assert ledger['pause_outside_office_minutes'] == 15
    assert ledger['remaining_statutory_minutes'] == 13
    assert ledger['deadline'] == 243


def test_deadline_path_crosses_future_closure_and_pause():
    ledger = projected(100, 130, 50, [(100, 140), (150, 200)], [(150, 155)])
    assert ledger['state'] == '尚可审理'
    assert ledger['deadline'] == 165
    assert ledger['future_charges'] == [
        {'from_minute': 130, 'until_minute': 140, 'charge_minutes': 10, 'remaining_before': 20, 'remaining_after': 10},
        {'from_minute': 155, 'until_minute': 165, 'charge_minutes': 10, 'remaining_before': 10, 'remaining_after': 0},
    ]


def test_missing_calendar_distinguishes_unknown_due_from_zero():
    ledger = projected(100, 120, 60, [(100, 140)])
    assert ledger['deadline'] is None
    assert ledger['uncovered_future_minutes'] == 20
    assert ledger['state'] == '日历覆盖不足'
    assert [item['charge_minutes'] for item in ledger['future_charges']] == [20]


@pytest.mark.parametrize(('asof', 'state', 'remaining'), [(120, '已到期', 0), (121, '已超时', -1)])
def test_exact_deadline_differs_from_lateness(asof, state, remaining):
    ledger = projected(100, asof, 20, [(100, 200)])
    assert ledger['state'] == state
    assert ledger['remaining_statutory_minutes'] == remaining
    assert ledger['deadline'] == 120 and ledger['future_charges'] == []


def test_same_minute_receipt_has_no_zero_length_segments():
    ledger = projected(150, 150, 30, [(100, 260)], [(130, 151)])
    assert ledger['timeline'] == []
    assert ledger['elapsed_wall_minutes'] == 0
    assert ledger['deadline'] == 181


def test_receipt_refuses_to_attest_to_different_counted_minutes():
    calendar = [(100, 160), (180, 210)]
    charge = balance('T-101', 90, 155, 60, calendar, [(140, 150)])
    with pytest.raises(ValueError, match='不一致'):
        office_projection(replace(charge, elapsed=99), 90, 155, calendar, [(140, 150)])


def test_missing_district_and_no_pauses_yields_uncovered_allotment():
    case = SimpleNamespace(permit=' no-office ', opened=100, district='偏远新区')
    clock = balance(case.permit, 100, 130, 70, (), ())
    [ledger] = clock_records([case], {case.permit: clock}, {}, {}, 130)
    assert ledger['timeline'] == [{'state': '窗口停办', 'start_minute': 100, 'end_minute': 130, 'minutes': 30}]
    assert ledger['uncovered_future_minutes'] == 70


def test_overlapping_breaks_cannot_double_charge_compensation_minutes():
    result = projected(100, 150, 30, [(100, 180)], [(110, 130), (118, 145)])
    assert result['paused_in_office_minutes'] == 35
    assert result['charged_minutes'] == 15
    assert result['deadline'] == 165
