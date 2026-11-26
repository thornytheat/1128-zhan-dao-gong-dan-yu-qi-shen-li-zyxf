"""Re-run an approved roster change and account for displaced appointments."""

from collections import Counter, defaultdict
from dataclasses import asdict
from hashlib import sha256
from json import dumps

from .staffing import solve


SCHEDULED = '安排复核'


def scenario_roster(roster, absences):
    roster_names = {row['handle'] for row in roster}
    if not isinstance(absences, dict) or not absences.keys() <= roster_names:
        raise ValueError('缺班人员须在已发布班表内')
    updated = []
    for person in roster:
        interval = absences.get(person['handle'])
        if interval is None and person['handle'] not in absences:
            updated.append(person)
            continue
        if not isinstance(interval, (list, tuple)) or len(interval) != 2 or any(type(t) is not int for t in interval):
            raise ValueError('缺班应有两个整数分钟端点')
        first, last = interval
        if first < 0 or first >= last:
            raise ValueError('缺班时间倒序或不合法')
        start = max(first, person['available'])
        end = min(last, person['shift_end'])
        if start < end:
            # 同一缺班重复套用不得重复占位：已登记的同段暂停直接保留。
            paused = [tuple(span) for span in person['paused']]
            if (start, end) not in paused:
                paused.append((start, end))
            updated.append(person | {'paused': paused})
        else:
            updated.append(person)
    return updated


def deadline_result(appointment, clock):
    if appointment.state != SCHEDULED:
        return '未排'
    if clock.due is None:
        return '日历待补'
    return '时限内' if appointment.finish <= clock.due else '超时结束'


def movement(previous, replacement):
    if previous == replacement:
        return '原安排'
    if previous.state == SCHEDULED and replacement.state != SCHEDULED:
        return '改为待审'
    if previous.state != SCHEDULED and replacement.state == SCHEDULED:
        return '补入班表'
    if (previous.reviewer, previous.second) != (replacement.reviewer, replacement.second):
        return '改派审理员'
    if (previous.start, previous.finish) != (replacement.start, replacement.finish):
        return '移动时段'
    return '变更原因'


def evidence_case(permit, clock, previous, replacement):
    first = deadline_result(previous, clock)
    second = deadline_result(replacement, clock)
    timing = None
    if previous.finish is not None and replacement.finish is not None:
        timing = replacement.finish - previous.finish
    return {
        'permit': permit.permit,
        'district': permit.district,
        'urgent': permit.urgent,
        'movement': movement(previous, replacement),
        'lawful_due_minute': clock.due,
        'original_finish_state': first,
        'proposed_finish_state': second,
        'finish_shift_minutes': timing,
        'lost_timely_review': first == '时限内' and second != '时限内',
        'original': asdict(previous),
        'proposed': asdict(replacement),
    }


def summarize(cases):
    districts = defaultdict(list)
    for row in cases:
        districts[row['district']].append(row)
    rollup = []
    for district, rows in sorted(districts.items()):
        changes = Counter(row['movement'] for row in rows)
        rollup.append({
            'district': district,
            'total': len(rows),
            'movement_counts': dict(sorted(changes.items())),
            'original_scheduled': sum(row['original']['state'] == SCHEDULED for row in rows),
            'proposed_scheduled': sum(row['proposed']['state'] == SCHEDULED for row in rows),
            'original_timely': sum(row['original_finish_state'] == '时限内' for row in rows),
            'proposed_timely': sum(row['proposed_finish_state'] == '时限内' for row in rows),
            'lost_timely_urgent': sum(row['urgent'] and row['lost_timely_review'] for row in rows),
        })
    return rollup


def shift_impact(cases, clocks, predictions, documents, roster, capacity, snapshot, baseline, absences):
    current = {row.permit: row for row in baseline}
    active = {row.permit: row for row in cases}
    if len(current) != len(baseline) or set(current) != set(active):
        raise ValueError('原有班表未逐一覆盖有效工单')
    changed = scenario_roster(roster, absences)
    alternative = solve(cases, clocks, predictions, documents, changed, capacity, snapshot)
    evidence = [evidence_case(active[row.permit], clocks[row.permit], current[row.permit], row) for row in alternative]
    totals = summarize(evidence)
    normalized_absences = {handle: list(span) for handle, span in sorted(absences.items())}
    receipt = {'record': '缺班影响复核', 'snapshot': snapshot, 'absence_minutes': normalized_absences,
               'capacity': capacity, 'districts': totals, 'changes': sum(row['movement'] != '原安排' for row in evidence)}
    material = dumps([receipt, evidence], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return receipt | {'replay_id': sha256(material.encode()).hexdigest()[:16], 'appointments': evidence}
