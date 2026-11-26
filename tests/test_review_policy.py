import pytest

from permitdesk.deadline_classifier.review_policy import capacity_replay, review_groups
from permitdesk.pipeline import run


def docket(permit, score, consumed, late, **setting):
    return {'permit': permit, 'score': score, 'statutory_share': consumed,
            'late': late, 'district': '路西', 'observed_minute': 100, 'reliability': '正常'} | setting


def test_observed_late_permits_explain_capacity_tradeoff():
    rows = [docket('T', .8, .6, True, district='河口'), docket('U', .3, 1., False), docket('V', .6, .2, True)]
    result = capacity_replay(rows, 2, .55)
    assert result['score_policy']['picked'] == ['T', 'V']
    assert result['statutory_time_policy']['picked'] == ['U', 'T']
    assert result['extra_late_caught'] == 1
    assert result['score_policy']['capture_rate'] == 1
    assert result['score_policy']['selected_per_district'] == {'河口': 1, '路西': 1}
    assert result['statutory_time_policy']['missed_late'] == ['V']


def test_cautious_scores_enter_manual_queue_ordered_by_lawful_time():
    rows = [docket('A', .99, .1, True, reliability='谨慎'), docket('B', .22, .8, False, reliability='谨慎'),
            docket('C', .65, .22, True), docket('D', .4, .95, False)]
    accepted, manual, low = review_groups(rows, .65)
    assert [row['permit'] for row in accepted] == ['C']
    assert [row['permit'] for row in manual] == ['B', 'A']
    assert [row['permit'] for row in low] == ['D']
    result = capacity_replay(rows, 2, .65)
    assert result['manual_review_count'] == 2
    assert result['score_policy']['picked'] == ['C', 'B']
    assert result['score_policy']['false_alarm_review'] == 1


def test_invariant_tie_resolution_and_complete_accounting():
    rows = [docket('B', .6, .8, True), docket('A', .6, .8, False),
            docket('C', .6, .8, False, observed_minute=99)]
    left = capacity_replay(rows, 2, .6)
    assert left == capacity_replay(rows[::-1], 2, .6)
    assert left['score_policy']['picked'] == ['C', 'A']
    assert left['score_policy']['missed_late'] == ['B']
    assert left['score_policy']['capture_rate'] == 0
    assert left['score_policy']['false_alarm_review'] == 2


def test_labels_are_only_used_after_selection():
    rows = [docket('P1', .8, .1, False), docket('P2', .4, .9, True)]
    measured = capacity_replay(rows, 1, .6)
    flipped = capacity_replay([row | {'late': not row['late']} for row in rows], 1, .6)
    assert measured['score_policy']['picked'] == flipped['score_policy']['picked']
    assert measured['statutory_time_policy']['picked'] == flipped['statutory_time_policy']['picked']
    assert measured['extra_late_caught'] == -1 and flipped['extra_late_caught'] == 1


def test_empty_and_nonpositive_cohorts_do_not_fake_a_rate():
    empty = capacity_replay([], 3, .5)
    assert empty['score_policy']['late_per_review'] is None
    assert empty['score_policy']['unused_slots'] == 3
    assert empty['extra_late_caught'] is None
    result = capacity_replay([docket('X', .72, .5, False)], 2, .5)
    assert result['score_policy']['capture_rate'] is None
    assert result['score_policy']['late_per_review'] == 0
    assert result['score_policy']['unused_slots'] == 1


@pytest.mark.parametrize(('slots','threshold'), [(True,.4), (0,.4), (101,.4), (3,True), (3,-.2), (3,float('nan'))])
def test_invalid_policy_limits_refused(slots, threshold):
    with pytest.raises(ValueError, match='回放'):
        capacity_replay([], slots, threshold)


def test_a_permit_cannot_consume_two_review_slots():
    row = docket('Z', .5, .5, True)
    with pytest.raises(ValueError, match='重复'):
        capacity_replay([row, row], 5, .5)


def test_workbench_capacity_changes_historical_review_capacity_not_frozen_scores():
    def windows(result):
        return [row for row in result['stages'][3]['records'] if 'from_minute' in row]
    low = windows(run(1))
    high = windows(run(15))
    measured = [(a, b) for a, b in zip(low, high, strict=True) if a['observations']]
    assert measured
    for first, second in measured:
        assert first['observations'] == second['observations']
        assert len(first['capacity_replay']['score_policy']['picked']) == 1
        assert len(second['capacity_replay']['score_policy']['picked']) == second['result']['sample_count']
