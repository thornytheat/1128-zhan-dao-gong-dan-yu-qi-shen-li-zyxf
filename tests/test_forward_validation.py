from dataclasses import replace

import pytest

from permitdesk.deadline_classifier.contracts import ModelPolicy
from permitdesk.deadline_classifier.forward_validation import calibration_loss, split_at, walk_forward
from permitdesk.review_features.contracts import EncodedSamples, ReviewVector


POLICY = ModelPolicy('roll-3', .04, 60, .16, .35, .65, 5, 1)


def observation(index):
    value = index % 10
    return ReviewVector(f'H-{index:02}', '北段' if index % 2 else '西段',
                        (value / 10, .1, .4, 0., .1, .3, 0.), value >= 6,
                        index * 10, index * 10 + 7)


def samples(rows=None):
    rows = list(rows) if rows is not None else [observation(index) for index in range(75)]
    return EncodedSamples(tuple(rows[:35]), tuple(rows[35:]), ())


def replay(rows=None, policy=POLICY, **change):
    settings = {'width': 100, 'calibration_minutes': 120, 'windows': 3, 'support': 12} | change
    return walk_forward(samples(rows), policy, 750, **settings)


def test_evaluation_uses_strict_detection_time_boundaries():
    output = replay()
    assert [row['from_minute'] for row in output] == [450, 550, 650]
    permits = []
    for window in output:
        assert window['state'] == '回放完成'
        assert window['latest_training_close'] < window['fit_before']
        assert window['fit_before'] <= window['latest_calibration_close'] < window['from_minute']
        assert window['result']['sample_count'] == 10
        assert sum(row['sample_count'] for row in window['districts']) == 10
        for row in window['observations']:
            assert row['model_as_of'] == window['from_minute']
            assert window['from_minute'] <= row['observed_minute'] < window['until_minute']
            assert row['closed_minute'] < 750
            permits.append(row['permit'])
    assert len(permits) == len(set(permits)) == 30


def test_post_cutoff_closure_is_ineligible_even_when_seen_in_validation_window():
    records = [observation(index) for index in range(75)]
    records.append(replace(records[-1], key='NOT-SETTLED', settled=750))
    assert replay(records) == replay()


def test_changed_outcome_changes_loss_but_never_its_frozen_score():
    rows = [observation(index) for index in range(75)]
    rows[47] = replace(rows[47], outcome=False)
    baseline, revised = replay()[0], replay(rows)[0]
    assert baseline['result']['late_count'] - revised['result']['late_count'] == 1
    assert [row['score'] for row in baseline['observations']] == [row['score'] for row in revised['observations']]
    assert baseline['result']['score_brier'] != revised['result']['score_brier']


def test_missing_calibration_history_remains_uncertified():
    results = replay(support=95)
    assert {row['state'] for row in results} == {'训练或校准不足'}
    assert all(row['result']['score_brier'] is None and not row['districts'] for row in results)


def test_absent_eligible_permits_has_a_distinct_state():
    rows = [observation(index) for index in range(45)]
    assert {row['state'] for row in replay(rows)} == {'无已结案观察'}


def test_duplicate_rows_agree_or_stop_review_without_order_preference():
    baseline = [observation(index) for index in range(75)]
    assert replay([*baseline[::-1], baseline[33]]) == replay()
    with pytest.raises(ValueError, match='矛盾'):
        replay([*baseline, replace(baseline[33], outcome=True)])


def test_split_does_not_include_exact_opening_minute():
    edge = [replace(observation(1), settled=minute) for minute in (79, 80, 99, 100)]
    verification = split_at(edge, 100, 20)
    assert [row.settled for row in verification.history] == [79]
    assert [row.settled for row in verification.calibration] == [80, 99]


@pytest.mark.parametrize('updates', [{'windows': 0}, {'width': True}, {'width': 751}, {'support': 1}])
def test_invalid_policy_window_fails_before_scoring(updates):
    with pytest.raises(ValueError, match='回放'):
        replay(**updates)


def test_brier_is_exact_for_known_pair_and_absent_for_empty_calendar():
    left = {'late': True, 'score': .7, 'reference_rate': .25, 'reliability': '正常'}
    right = dict(left, late=False, score=.4, reliability='谨慎')
    score = calibration_loss([left, right])
    assert score['score_brier'] == pytest.approx((.3 ** 2 + .4 ** 2) / 2)
    assert score['reference_brier'] == pytest.approx((.75 ** 2 + .25 ** 2) / 2)
    assert score['review_only'] == 1
    assert calibration_loss([])['realized_late_rate'] is None
