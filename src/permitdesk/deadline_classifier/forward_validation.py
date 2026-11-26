"""Audit score calibration on time-separated, already closed permits."""

from collections import defaultdict
from dataclasses import dataclass
from math import fsum

from .classifier import assess, fit
from .review_policy import capacity_replay


@dataclass(frozen=True)
class ReplaySamples:
    history: tuple
    calibration: tuple


def split_at(rows, opening, calibration_minutes):
    boundary = opening - calibration_minutes
    history = tuple(row for row in rows if row.settled < boundary)
    calibration = tuple(row for row in rows if boundary <= row.settled < opening)
    return ReplaySamples(history, calibration)


def unique_closed(samples, cutoff):
    seen = {}
    for row in (*samples.history, *samples.calibration):
        if row.settled is None or row.settled >= cutoff:
            continue
        if row.outcome is None or row.settled < row.visible:
            raise ValueError('回放要求已结案且观察时点早于结案')
        if row.key in seen and seen[row.key] != row:
            raise ValueError('回放中发现相互矛盾的工单观察')
        seen[row.key] = row
    return sorted(seen.values(), key=lambda row: (row.visible, row.key))


def evidence_row(row, model, baseline, opening):
    note = assess(model, row)
    return {
        'permit': row.key,
        'district': row.zone,
        'observed_minute': row.visible,
        'closed_minute': row.settled,
        'model_as_of': opening,
        'late': row.outcome,
        'score': note.probability,
        'raw_score': note.raw,
        'statutory_share': row.values[0],
        'reference_rate': baseline,
        'reliability': note.reliability,
    }


def calibration_loss(rows):
    if not rows:
        return {'sample_count': 0, 'late_count': 0, 'score_brier': None,
                'reference_brier': None, 'mean_score': None, 'realized_late_rate': None,
                'review_only': 0}
    count = len(rows)
    late = sum(row['late'] for row in rows)
    return {
        'sample_count': count,
        'late_count': late,
        'score_brier': fsum((row['score'] - row['late']) ** 2 for row in rows) / count,
        'reference_brier': fsum((row['reference_rate'] - row['late']) ** 2 for row in rows) / count,
        'mean_score': fsum(row['score'] for row in rows) / count,
        'realized_late_rate': late / count,
        'review_only': sum(row['reliability'] != '正常' for row in rows),
    }


def compare_districts(rows):
    partition = defaultdict(list)
    for row in rows:
        partition[row['district']].append(row)
    return [{'district': district, **calibration_loss(entries)} for district, entries in sorted(partition.items())]


def replay_window(rows, policy, opening, closing, calibration_minutes, support, review_slots):
    training = split_at(rows, opening, calibration_minutes)
    validation = tuple(row for row in rows if opening <= row.visible < closing)
    classes = {row.outcome for row in training.history}
    enough_support = len(training.history) >= support and len(classes) == 2 and bool(training.calibration)
    details = []
    if enough_support and validation:
        model = fit(training, policy)
        prior = (model.labels + 1) / (model.train + 2)
        details = [evidence_row(row, model, prior, opening) for row in validation]
    state = '回放完成' if details else '无已结案观察' if not validation else '训练或校准不足'
    return {
        'from_minute': opening,
        'until_minute': closing,
        'fit_before': opening - calibration_minutes,
        'history_count': len(training.history),
        'calibration_count': len(training.calibration),
        'closed_observations': len(validation),
        'latest_training_close': max((row.settled for row in training.history), default=None),
        'latest_calibration_close': max((row.settled for row in training.calibration), default=None),
        'state': state,
        'result': calibration_loss(details),
        'districts': compare_districts(details),
        'capacity_replay': capacity_replay(details, review_slots, policy.cut_high),
        'observations': details,
    }


def walk_forward(samples, policy, cutoff, *, width=240, calibration_minutes=360, windows=4, support=8, review_slots=8):
    if any(type(value) is not int or value < 1 for value in (cutoff, width, calibration_minutes, windows, support)):
        raise ValueError('回放配置须为正整数')
    if windows > 20 or width * windows > cutoff or support < 2:
        raise ValueError('回放范围或训练下限不合法')
    rows = unique_closed(samples, cutoff)
    return [
        replay_window(rows, policy, opening, opening + width, calibration_minutes, support, review_slots)
        for opening in range(cutoff - width * windows, cutoff, width)
    ]
