import pytest
from types import SimpleNamespace

from permitdesk.review_roster.shift_replay import scenario_roster, shift_impact
from permitdesk.review_roster.staffing import solve


def employee(handle, shift=(100, 250), **changes):
    return {'handle': handle, 'district': '东区', 'skills': ['抢修'], 'available': shift[0], 'shift_end': shift[1],
            'allow_emergency': True, 'stock': 4, 'paused': [], 'second_sign': True} | changes


def permit(name, urgent=True, lanes=1, district='东区'):
    return SimpleNamespace(permit=name, district=district, work='抢修', lanes=lanes, urgent=urgent, obstruction=20)


def compare(cases, people, absences, cap=5, until=150, expected=None):
    clocks = {case.permit: SimpleNamespace(overdue=False, remaining=until - 100, due=until) for case in cases}
    scores = {case.permit: SimpleNamespace(probability=.7) for case in cases}
    docs = {case.permit: () for case in cases}
    baseline = solve(cases, clocks, scores, docs, people, cap, 100) if expected is None else expected
    return shift_impact(cases, clocks, scores, docs, people, cap, 100, baseline, absences)


def test_total_absence_removes_urgent_timely_review_with_no_qualified_backup():
    result = compare([permit('A')], [employee('姜'), employee('章', district='西区')], {'姜': [100, 250]})
    [slot] = result['appointments']
    assert slot['movement'] == '改为待审'
    assert slot['original']['reviewer'] == '姜'
    assert slot['proposed']['state'] == '主管协调'
    assert slot['original_finish_state'] == '时限内' and slot['proposed_finish_state'] == '未排'
    assert slot['lost_timely_review']
    assert result['districts'][0]['lost_timely_urgent'] == 1


def test_near_deadline_reassignment_preserves_double_signature_with_two_people():
    people = [employee('甲'), employee('乙', shift=(105, 250)), employee('丙', shift=(106, 250))]
    result = compare([permit('T', lanes=3)], people, {'甲': [100, 250]}, until=151)
    slot = result['appointments'][0]
    assert slot['movement'] == '改派审理员'
    assert slot['original']['finish'] == 150
    assert slot['proposed']['finish'] == 155
    assert len({slot['proposed']['reviewer'], slot['proposed']['second']}) == 2
    assert slot['proposed_finish_state'] == '超时结束'
    assert slot['finish_shift_minutes'] == 5


def test_short_absence_between_slots_does_not_reduce_quota():
    people = [employee('甲', paused=[[155, 160]])]
    results = compare([permit('A'), permit('B', urgent=False)], people, {'甲': [125, 148]}, until=220)
    original, moved = results['appointments']
    assert original['movement'] == '原安排'
    assert moved['movement'] == '移动时段'
    assert moved['original']['start'] == 125
    assert moved['proposed']['start'] == 160


def test_no_change_for_entirely_outside_shift_and_replay_id_contains_what_if():
    cases = [permit('A')]
    roster = [employee('马')]
    default = compare(cases, roster, {})
    outside = compare(cases, roster, {'马': [251, 290]})
    assert default['appointments'] == outside['appointments']
    assert outside['changes'] == 0
    assert default['replay_id'] != outside['replay_id']


def test_shift_changes_are_stable_when_dockets_and_roster_are_permuted():
    people = [employee('周'), employee('甲')]
    calls = [permit('D1'), permit('D2', urgent=False)]
    blocked = {'周': [101, 112], '甲': [130, 150]}
    left = compare(calls, people, blocked, cap=1)
    right = compare(calls[::-1], people[::-1], dict(reversed(list(blocked.items()))), cap=1)
    assert left == right
    assert left['districts'][0]['total'] == 2


@pytest.mark.parametrize('invalid', [{'另人': [100, 190]}, {'周': None}, {'周': [100]}, {'周': [True, 5]}, {'周': [180, 120]}])
def test_bad_absence_intervals_never_rewrite_published_schedule(invalid):
    roster = [employee('周')]
    with pytest.raises(ValueError, match='缺班'):
        scenario_roster(roster, invalid)
    assert roster[0]['paused'] == []


def test_docket_change_after_snapshot_detected_before_rescheduling():
    with pytest.raises(ValueError, match='逐一覆盖'):
        compare([permit('A')], [employee('周')], {}, expected=())
