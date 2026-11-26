"""Measure missed late permits when only part of a closed cohort was reviewable."""

from collections import Counter
from math import isfinite


def time_order(row):
    return (-row['statutory_share'], row['observed_minute'], row['permit'])


def model_order(row):
    return (-row['score'], *time_order(row))


def review_groups(rows, threshold):
    eligible = []
    low = []
    cautious = []
    for row in rows:
        if row['reliability'] != '正常':
            cautious.append(row)
        elif row['score'] >= threshold:
            eligible.append(row)
        else:
            low.append(row)
    return sorted(eligible, key=model_order), sorted(cautious, key=time_order), sorted(low, key=time_order)


def outcomes(rows, selected, slots):
    keys = {row['permit'] for row in selected}
    selected_late = sum(row['late'] for row in selected)
    total_late = sum(row['late'] for row in rows)
    by_zone = Counter(row['district'] for row in selected)
    missed = sorted(row['permit'] for row in rows if row['late'] and row['permit'] not in keys)
    return {
        'picked': [row['permit'] for row in selected],
        'selected_late': selected_late,
        'false_alarm_review': len(selected) - selected_late,
        'missed_late': missed,
        'unused_slots': slots - len(selected),
        'capture_rate': selected_late / total_late if total_late else None,
        'late_per_review': selected_late / len(selected) if selected else None,
        'selected_per_district': dict(sorted(by_zone.items())),
    }


def capacity_replay(rows, slots, threshold):
    if type(slots) is not int or not 1 <= slots <= 100:
        raise ValueError('回放审理席位超出范围')
    if isinstance(threshold, bool) or not isinstance(threshold, (float, int)) or not isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('回放概率阈值超出范围')
    if len({row['permit'] for row in rows}) != len(rows):
        raise ValueError('同一回放工单重复进入审理')
    likely, review_only, low_risk = review_groups(rows, threshold)
    proposed = [*likely, *review_only, *low_risk][:slots]
    baseline = sorted(rows, key=time_order)[:slots]
    compared = outcomes(rows, proposed, slots)
    reference = outcomes(rows, baseline, slots)
    return {
        'slots': slots,
        'threshold': threshold,
        'cohort_count': len(rows),
        'manual_review_count': len(review_only),
        'high_risk_count': len(likely),
        'score_policy': compared,
        'statutory_time_policy': reference,
        'extra_late_caught': compared['selected_late'] - reference['selected_late'] if rows else None,
    }
