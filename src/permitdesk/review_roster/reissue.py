"""缺班后重出本班复核安排的裁决引擎。

裁决纪律：
1. 已告知且不受缺班影响的预约一律保留，不悄悄挪动。
2. 受缺班冲击的预约先尝试班内改派，优先选出能在法定截止前完审的组合；
   无法在班内安置的工单退回主管协调，并释放一个补位席位。
3. 释放席位只能给本班基线尚未安排的工单，补位顺序仍看逾期风险与法定剩余时间。
4. 需双签的工单无论改派还是补位，都必须由两名不同审理员在班内完成。
5. 改派/补位只追加新的告知凭据，原告知记录保留并被新凭据引用。
6. 同一输入重跑得到完全一致的结果且不会重复占位、重复告知。
"""

from collections import defaultdict
from dataclasses import asdict
from hashlib import sha256
from json import dumps

from .contracts import Appointment
from .notice_ledger import NoticeLedger
from .shift_replay import SCHEDULED, deadline_result, movement, scenario_roster
from .staffing import (
    case_cost,
    hold,
    parse_roster,
    pending_order,
    slot_combinations,
)


RETAIN = '保留原约'
REASSIGN = '改派'
DROP = '退回主管协调'
BACKFILL = '补位入班'
HOLD_MISSING = '材料待补未补位'
HOLD_BUDGET = '无释放席位未补位'
HOLD_NO_SLOT = '班内无组合未补位'


def effective_absence(person, span):
    start = max(span[0], person.available)
    end = min(span[1], person.shift_end)
    return start, end


def overlaps(start, finish, span):
    blocked_start, blocked_end = span
    return start < blocked_end and blocked_start < finish


def _blocked_handles(appointment, absence_spans):
    handles = [appointment.reviewer]
    if appointment.second is not None:
        handles.append(appointment.second)
    return {handle for handle in handles
            if handle in absence_spans
            and overlaps(appointment.start, appointment.finish, absence_spans[handle])}


def _timely(combo, clock):
    if clock.due is None:
        return False
    return combo[0] <= clock.due


def choose_combination(combinations, clock):
    """法定时限优先：先在时限内组合里取最早完审，否则取全部组合里最早完审。"""
    timely = [combo for combo in combinations if _timely(combo, clock)]
    pool = timely or combinations
    return min(pool), bool(timely)


def commit(combo, cursors, used):
    end, start, primary, secondary, primary_end, _secondary_start = combo
    cursors[primary] = primary_end
    used[primary] += 1
    if secondary is not None:
        cursors[secondary] = end
        used[secondary] += 1
    return Appointment('', SCHEDULED, primary, secondary, start, end, '资质及班内时段可用')


def decision_record(permit, clock, previous, replacement, ruling, notice, detail):
    return {
        'permit': permit,
        'ruling': ruling,
        'movement': movement(previous, replacement),
        'lawful_due_minute': clock.due,
        'original_finish_state': deadline_result(previous, clock),
        'proposed_finish_state': deadline_result(replacement, clock),
        'notice_id': notice.notice_id if notice else None,
        'superseded_notice_id': notice.supersedes if notice else None,
        'detail': detail,
        'original': asdict(previous),
        'proposed': asdict(replacement),
    }


def reissue_token(decisions, absence_minutes, ledger, capacity):
    payload = {
        'absence_minutes': {k: list(v) for k, v in sorted(absence_minutes.items())},
        'capacity': capacity,
        'decisions': [{k: row[k] for k in ('permit', 'ruling', 'proposed', 'notice_id')}
                      for row in decisions],
        'notice_ids': [entry.notice_id for entry in ledger.entries],
    }
    material = dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return sha256(material.encode()).hexdigest()[:16]


def reissue_roster(permits, clocks, scores, missing, roster, capacity, asof,
                   baseline, absences, issued_minute, ledger=None):
    """按缺班事实重出本班安排并裁决每张工单的去留。

    ``ledger`` 可传入已含首版告知的台账；不传则按基线已安排工单补发首版告知。
    返回 (新班表 Appointment 元组, 裁决记录, 告知台账, 重跑令牌)。
    """
    people = parse_roster(scenario_roster(roster, absences))
    base_by_permit = {row.permit: row for row in baseline}
    if len(base_by_permit) != len(baseline):
        raise ValueError('基线班表存在重复工单')
    active_permits = {case.permit for case in permits}
    if set(base_by_permit) != active_permits:
        raise ValueError('原有班表未逐一覆盖有效工单')

    absence_spans = {}
    for person in people:
        if person.handle in absences:
            span = effective_absence(person, absences[person.handle])
            if span[0] < span[1]:
                absence_spans[person.handle] = span

    journal = ledger if ledger is not None else NoticeLedger(issued_minute)
    if ledger is None:
        for row in baseline:
            if row.state == SCHEDULED:
                journal.record_initial(row.permit, row)

    cursors = {item.handle: asof for item in people}
    used = defaultdict(int)
    decisions = []
    replacement_by_permit = {}
    displaced = 0

    # 第一步：已告知预约——未受缺班冲击的原样保留并预先占住审理员游标。
    baseline_scheduled = [row for row in baseline if row.state == SCHEDULED]
    blocked_rows = []
    for row in baseline_scheduled:
        blocked = _blocked_handles(row, absence_spans)
        if not blocked:
            retained = Appointment(row.permit, row.state, row.reviewer, row.second,
                                   row.start, row.finish, row.reason)
            replacement_by_permit[row.permit] = retained
            cursors[row.reviewer] = max(cursors[row.reviewer], row.finish)
            used[row.reviewer] += 1
            if row.second is not None:
                cursors[row.second] = max(cursors[row.second], row.finish)
                used[row.second] += 1
            decisions.append(decision_record(
                row.permit, clocks[row.permit], row, retained, RETAIN,
                journal.latest(row.permit), '预约时段不与缺班交集，原约保留不挪动'))
        else:
            blocked_rows.append((row, blocked))

    case_by_permit = {case.permit: case for case in permits}

    # 第二步：受冲击预约——班内改派，时限内组合优先；安置不了则退回并释放席位。
    for row, blocked in blocked_rows:
        case = case_by_permit[row.permit]
        clock = clocks[row.permit]
        combinations = slot_combinations(case, people, cursors, used)
        previous_notice = journal.latest(row.permit)
        if not combinations:
            pending = hold(row.permit, '主管协调', '缺班后班表内没有符合辖区资质和签审人数的组合')
            displaced += 1
            decisions.append(decision_record(
                row.permit, clock, row, pending, DROP, None,
                '缺班审理员：' + '、'.join(sorted(blocked)) + '；班内无可用组合，释放补位席位'))
            replacement_by_permit[row.permit] = pending
            continue
        combo, on_time = choose_combination(combinations, clock)
        appointment = commit(combo, cursors, used)
        appointment = Appointment(row.permit, appointment.state, appointment.reviewer,
                                  appointment.second, appointment.start, appointment.finish,
                                  appointment.reason)
        reason = '缺班改派，优先法定时限内组合' if on_time else '缺班改派，时限内无组合取最早完审'
        notice = journal.record_reassignment(row.permit, appointment, previous_notice, reason)
        decisions.append(decision_record(
            row.permit, clock, row, appointment, REASSIGN, notice, reason))
        replacement_by_permit[row.permit] = appointment

    # 第三步：释放席位只补给本班基线尚未安排的工单，顺序仍看逾期风险和法定剩余时间。
    backfill_budget = displaced
    unscheduled = [case_by_permit[row.permit] for row in baseline if row.state != SCHEDULED]
    for case in sorted(unscheduled,
                       key=lambda item: pending_order(item, clocks[item.permit], scores[item.permit])):
        previous = base_by_permit[case.permit]
        clock = clocks[case.permit]
        if missing[case.permit] and not case.urgent:
            pending = hold(case.permit, '通知补件', '材料仍缺：' + '、'.join(missing[case.permit]))
            decisions.append(decision_record(
                case.permit, clock, previous, pending, HOLD_MISSING, None,
                '材料未齐且非应急，不参与缺班补位'))
            replacement_by_permit[case.permit] = pending
            continue
        if backfill_budget <= 0:
            pending = hold(case.permit, previous.state, '缺班未释放可补位席位')
            decisions.append(decision_record(
                case.permit, clock, previous, pending, HOLD_BUDGET, None,
                '补位席位已用完，维持基线待审状态'))
            replacement_by_permit[case.permit] = pending
            continue
        combinations = slot_combinations(case, people, cursors, used)
        if not combinations:
            pending = hold(case.permit, '主管协调', '班表内没有符合辖区资质和签审人数的组合')
            decisions.append(decision_record(
                case.permit, clock, previous, pending, HOLD_NO_SLOT, None,
                '有释放席位但班内无可用组合'))
            replacement_by_permit[case.permit] = pending
            continue
        combo, on_time = choose_combination(combinations, clock)
        appointment = commit(combo, cursors, used)
        appointment = Appointment(case.permit, appointment.state, appointment.reviewer,
                                  appointment.second, appointment.start, appointment.finish,
                                  appointment.reason)
        backfill_budget -= 1
        reason = '缺班释放席位补位，优先法定时限内组合' if on_time else '缺班释放席位补位，时限内无组合取最早完审'
        notice = journal.record_backfill(case.permit, appointment, reason)
        decisions.append(decision_record(
            case.permit, clock, previous, appointment, BACKFILL, notice, reason))
        replacement_by_permit[case.permit] = appointment

    reissued = tuple(replacement_by_permit[case.permit] for case in permits)
    token = reissue_token(decisions, absences, journal, capacity)
    return reissued, decisions, journal, token


def reissue_summary(decisions):
    counts = defaultdict(int)
    for row in decisions:
        counts[row['ruling']] += 1
    scheduled = sum(row['proposed']['state'] == SCHEDULED for row in decisions)
    timely = sum(row['proposed_finish_state'] == '时限内' for row in decisions)
    return {
        'record': '缺班重排裁决汇总',
        'ruling_counts': dict(sorted(counts.items())),
        'proposed_scheduled': scheduled,
        'proposed_timely': timely,
        'retained': counts[RETAIN],
        'reassigned': counts[REASSIGN],
        'dropped': counts[DROP],
        'backfilled': counts[BACKFILL],
    }
