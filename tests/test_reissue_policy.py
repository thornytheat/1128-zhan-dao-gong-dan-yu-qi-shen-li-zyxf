"""缺班重排裁决的纪律测试。

覆盖：已告知时段不被悄悄挪动、改派留下新凭据且旧凭据保留、释放席位只给
本班未安排工单、补位看逾期风险和法定剩余时间、双签须两名不同审理员在班内
完成，以及同一缺班重跑不重复占位。
"""

from types import SimpleNamespace

import pytest

from permitdesk.review_roster.notice_ledger import (
    BACKFILL_KIND,
    INITIAL_KIND,
    REASSIGN_KIND,
    NoticeLedger,
)
from permitdesk.review_roster.reissue import (
    BACKFILL,
    DROP,
    REASSIGN,
    RETAIN,
    reissue_roster,
)
from permitdesk.review_roster.service import baseline_notice_ledger
from permitdesk.review_roster.shift_replay import SCHEDULED
from permitdesk.review_roster.staffing import solve


def employee(handle, shift=(100, 260), **changes):
    return {'handle': handle, 'district': '东区', 'skills': ['抢修'],
            'available': shift[0], 'shift_end': shift[1],
            'allow_emergency': True, 'stock': 4, 'paused': [],
            'second_sign': True} | changes


def permit(name, urgent=True, lanes=1, district='东区', obstruction=20, work='抢修'):
    return SimpleNamespace(permit=name, district=district, work=work,
                           lanes=lanes, urgent=urgent, obstruction=obstruction)


def clock(until, remaining=None, overdue=False):
    return SimpleNamespace(overdue=overdue,
                           remaining=(until - 100) if remaining is None else remaining,
                           due=until)


def setup(cases, people, cap=6, due=200, asof=100, docs=None):
    clocks = {case.permit: clock(due) for case in cases}
    scores = {case.permit: SimpleNamespace(probability=.7) for case in cases}
    missing = docs or {case.permit: () for case in cases}
    baseline = solve(cases, clocks, scores, missing, people, cap, asof)
    ledger = baseline_notice_ledger(baseline, asof)
    return clocks, scores, missing, baseline, ledger


def reissue(cases, people, absences, cap=6, due=200, asof=100, docs=None):
    clocks, scores, missing, baseline, ledger = setup(cases, people, cap, due, asof, docs)
    reissued, decisions, journal, token = reissue_roster(
        cases, clocks, scores, missing, people, cap, asof, baseline,
        absences, asof, ledger)
    return SimpleNamespace(reissued=reissued, decisions=decisions, journal=journal,
                           token=token, baseline=baseline, clocks=clocks, ledger=ledger,
                           original_notices=[n for n in ledger.entries])


def by_permit(rows, key='permit'):
    return {row[key]: row for row in rows}


def test_unaffected_notified_appointment_is_retained_untouched():
    cases = [permit('A')]
    people = [employee('甲'), employee('乙')]
    baseline_reviewer = setup(cases, people)[3][0].reviewer
    other = next(person['handle'] for person in people
                 if person['handle'] != baseline_reviewer)
    out = reissue(cases, people, {other: [100, 260]})
    [decision] = out.decisions
    assert decision['ruling'] == RETAIN
    assert decision['proposed'] == decision['original']
    # 保留原约不产生新告知，沿用首版凭据。
    assert decision['notice_id'] == out.ledger.latest('A').notice_id
    assert [n.kind for n in out.journal.entries] == [INITIAL_KIND]


def test_blocked_appointment_is_reassigned_with_new_notice_chain():
    cases = [permit('A')]
    people = [employee('甲'), employee('乙', shift=(105, 260))]
    baseline_reviewer = setup(cases, people)[3][0].reviewer
    out = reissue(cases, people, {baseline_reviewer: [100, 260]})
    [decision] = out.decisions
    assert decision['ruling'] == REASSIGN
    assert decision['proposed']['reviewer'] != baseline_reviewer
    new_notice = out.journal.latest('A')
    old_notice = out.original_notices[0]
    assert new_notice.kind == REASSIGN_KIND
    assert new_notice.supersedes == old_notice.notice_id
    # 原有告知记录仍在台账里，没有被删除或覆盖。
    assert old_notice in out.journal.entries
    assert [n.notice_id for n in out.journal.entries] == [old_notice.notice_id, new_notice.notice_id]
    assert decision['notice_id'] == new_notice.notice_id
    assert decision['superseded_notice_id'] == old_notice.notice_id


def test_reassignment_prefers_combination_finishing_before_statutory_due():
    # 两个备选：早班与晚班审理员；法定截止只够早班的时段。
    cases = [permit('A')]
    people = [employee('甲', shift=(100, 260)), employee('乙', shift=(100, 260)),
              employee('丙', shift=(200, 260))]
    clocks, scores, missing, baseline, ledger = setup(cases, people, due=180)
    baseline_reviewer = baseline[0].reviewer
    _reissued, decisions, _journal, _token = reissue_roster(
        cases, clocks, scores, missing, people, 6, 100, baseline,
        {baseline_reviewer: [100, 260]}, 100, ledger)
    assert decisions[0]['proposed_finish_state'] == '时限内'
    assert decisions[0]['proposed']['finish'] <= 180


def test_unresolvable_blocked_case_drops_and_releases_one_backfill_seat():
    # 双签工单（3 车道）基线由甲乙两人会签；其中一人缺班后无人可凑齐双签。
    blocked = permit('T', lanes=3)
    waiting = permit('W', urgent=False)
    people = [employee('甲'), employee('乙')]
    baseline = setup([blocked, waiting], people, cap=1)[3]
    absent = baseline[0].reviewer
    out = reissue([blocked, waiting], people, {absent: [100, 260]}, cap=1)
    rulings = by_permit(out.decisions)
    assert rulings['T']['ruling'] == DROP
    assert rulings['T']['proposed']['state'] == '主管协调'
    # 释放的一个席位只能给本班基线未安排的 W，而不是再塞第二张新单。
    assert rulings['W']['ruling'] == BACKFILL
    assert rulings['W']['proposed']['state'] == SCHEDULED
    assert sum(r['proposed']['state'] == SCHEDULED for r in out.decisions) == 1


def test_backfill_only_draws_from_shift_unscheduled_dockets():
    scheduled = permit('S')
    waiting = permit('W', urgent=False)
    people = [employee('甲'), employee('乙')]
    baseline = setup([scheduled, waiting], people, cap=1)[3]
    absent = baseline[0].reviewer
    out = reissue([scheduled, waiting], people, {absent: [100, 260]}, cap=1)
    rulings = by_permit(out.decisions)
    # 原工单改派给另一人，未释放席位；基线未安排的 W 不得借机入班。
    assert rulings['S']['ruling'] == REASSIGN
    assert rulings['W']['ruling'] == '无释放席位未补位'
    assert rulings['W']['proposed']['state'] != SCHEDULED


def test_backfill_priority_follows_overdue_risk_and_statutory_remaining():
    # 甲独掌抢修技能（B 为抢修应急），乙只能做普通施工；甲缺班后 B 退回释放席位，
    # 乙可承接普通工单，用于检验补位是否按法定剩余时间排序。
    people = [employee('甲'), employee('乙', allow_emergency=False, skills=['普通'])]
    blocked = permit('B')
    near = permit('N', urgent=False, work='普通')
    later = permit('L', urgent=False, work='普通')
    cases = [blocked, near, later]
    clocks = {name: clock(200) for name in ('B', 'N', 'L')}
    clocks['N'].remaining = 5
    clocks['L'].remaining = 80
    scores = {name: SimpleNamespace(probability=.7) for name in ('B', 'N', 'L')}
    missing = {name: () for name in ('B', 'N', 'L')}
    baseline = solve(cases, clocks, scores, missing, people, 1, 100)
    absent = baseline[0].reviewer
    ledger = baseline_notice_ledger(baseline, 100)
    _reissued, decisions, _journal, _token = reissue_roster(
        cases, clocks, scores, missing, people, 1, 100, baseline,
        {absent: [100, 260]}, 100, ledger)
    rulings = by_permit(decisions)
    assert rulings['B']['ruling'] == DROP
    assert rulings['N']['ruling'] == BACKFILL  # 剩余法定时间更短者先补
    assert rulings['L']['ruling'] == '无释放席位未补位'


def test_double_signature_case_keeps_two_distinct_in_shift_reviewers_after_reassignment():
    cases = [permit('T', lanes=3)]
    people = [employee('甲'), employee('乙', shift=(105, 260)),
              employee('丙', shift=(106, 260))]
    baseline = setup(cases, people)[3]
    absent = baseline[0].reviewer
    out = reissue(cases, people, {absent: [100, 260]})
    slot = out.decisions[0]['proposed']
    assert slot['second'] is not None
    assert slot['reviewer'] != slot['second']
    assert slot['start'] >= 100 and slot['finish'] <= 260


def test_double_signature_backfill_also_requires_two_distinct_reviewers():
    blocked = permit('B', lanes=3)
    waiting = permit('W', lanes=3, urgent=False)
    # 只有甲乙两人且都能二审：cap=1 时 B 占住双签名额，W 留在基线待审。
    people = [employee('甲'), employee('乙')]
    baseline = setup([blocked, waiting], people, cap=1)[3]
    absent = baseline[0].reviewer
    out = reissue([blocked, waiting], people, {absent: [100, 260]}, cap=1)
    rulings = by_permit(out.decisions)
    assert rulings['B']['ruling'] == DROP
    # 待审的双签工单补位时同样要两名不同审理员，凑不齐则不得入班、不发告知。
    assert rulings['W']['ruling'] == '班内无组合未补位'
    assert rulings['W']['proposed']['state'] == '主管协调'
    assert rulings['W']['notice_id'] is None


def test_same_absence_rerun_is_identical_and_does_not_duplicate_seats_or_notices():
    cases = [permit('A'), permit('B', urgent=False)]
    people = [employee('甲'), employee('乙')]
    absent = setup(cases, people)[3][0].reviewer
    absences = {absent: [100, 260]}
    first = reissue(cases, people, absences)
    second = reissue(cases, people, absences)
    assert first.token == second.token
    assert first.reissued == second.reissued
    assert first.decisions == second.decisions
    assert [n.notice_id for n in first.journal.entries] == \
           [n.notice_id for n in second.journal.entries]
    # 班内不会出现同一工单的重复预约。
    permits = [row.permit for row in second.reissued if row.state == SCHEDULED]
    assert len(permits) == len(set(permits))


def test_repeated_reissue_into_same_ledger_dedupicates_identical_notices():
    cases = [permit('A')]
    people = [employee('甲'), employee('乙')]
    clocks, scores, missing, baseline, ledger = setup(cases, people)
    absent = baseline[0].reviewer
    args = (cases, clocks, scores, missing, people, 6, 100, baseline)
    r1, d1, journal1, _token1 = reissue_roster(*args, {absent: [100, 260]}, 100, ledger)
    # 把第一次重排结果当作新基线再跑同一缺班：告知内容相同不得重复追加。
    before = len(journal1.entries)
    r2, d2, journal2, _token2 = reissue_roster(
        cases, clocks, scores, missing, people, 6, 100, r1,
        {absent: [100, 260]}, 100, journal1)
    assert len(journal2.entries) == before
    # 第二次重排没有新的改动（第一次的结果已避开缺班），裁决全部为保留。
    assert all(row['ruling'] == RETAIN for row in d2)
    assert r2 == r1


def test_original_notice_cannot_be_deleted_and_ledger_is_append_only():
    ledger = NoticeLedger(100)
    with pytest.raises(AttributeError):
        ledger.entries = ()
    cases = [permit('A')]
    people = [employee('甲'), employee('乙')]
    absent = setup(cases, people)[3][0].reviewer
    out = reissue(cases, people, {absent: [100, 260]})
    initial = [n for n in out.journal.entries if n.kind == INITIAL_KIND]
    assert len(initial) == 1 and initial[0].permit == 'A'
    kinds = [n.kind for n in out.journal.entries]
    assert kinds == [INITIAL_KIND, REASSIGN_KIND]


def test_missing_material_non_urgent_docket_never_takes_backfill_seat():
    blocked = permit('B')
    waiting = permit('M', urgent=False)
    # 唯一同辖区审理员缺班后无人可顶，B 必然退回并释放一个席位。
    people = [employee('甲'), employee('乙', district='西区')]
    docs = {'B': (), 'M': ('道路占挖告知函',)}
    absent = setup([blocked, waiting], people, cap=1, docs=docs)[3][0].reviewer
    out = reissue([blocked, waiting], people, {absent: [100, 260]}, cap=1, docs=docs)
    rulings = by_permit(out.decisions)
    assert rulings['B']['ruling'] == DROP
    assert rulings['M']['ruling'] == '材料待补未补位'
    assert rulings['M']['proposed']['state'] == '通知补件'
    # 释放席位宁可空着也不被材料不齐的非应急工单占用。
    assert sum(r['proposed']['state'] == SCHEDULED for r in out.decisions) == 0


def test_backfill_notice_is_a_distinct_new_receipt():
    blocked = permit('B')
    waiting = permit('W', urgent=False, work='普通')
    # 甲独掌抢修（B 无人可顶必然退回），乙承接普通工单 W 的补位。
    people = [employee('甲'), employee('乙', allow_emergency=False, skills=['普通'])]
    absent = setup([blocked, waiting], people, cap=1)[3][0].reviewer
    out = reissue([blocked, waiting], people, {absent: [100, 260]}, cap=1)
    notice = out.journal.latest('W')
    assert notice.kind == BACKFILL_KIND and notice.supersedes is None


def test_invalid_absence_is_rejected_before_any_schedule_change():
    cases = [permit('A')]
    people = [employee('甲')]
    clocks, scores, missing, baseline, ledger = setup(cases, people)
    roster_snapshot = [dict(row) for row in people]
    with pytest.raises(ValueError, match='缺班'):
        reissue_roster(cases, clocks, scores, missing, people, 6, 100, baseline,
                       {'陌生人': [100, 200]}, 100, ledger)
    assert people == roster_snapshot
