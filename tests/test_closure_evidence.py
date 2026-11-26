from types import SimpleNamespace

import pytest

from permitdesk.permit_journal.closure_evidence import review_closures
from permitdesk.review_roster.contracts import Appointment


def posted(permit='L1', recorded=180, **changes):
    return {'permit': permit, 'submitted': 110, 'recorded': recorded, 'late': False, 'signature': '马二审',
            'disposition': '已会签', 'primary': '于首审', 'ticket': permit + '-1'} | changes


def scheduled(permit='L1', finish=165):
    return Appointment(permit, '安排复核', '于首审', '马二审', 120, finish, '资质时段匹配')


def compare(records, orders=None, clocks=None, cutoff=210):
    orders = [scheduled()] if orders is None else orders
    clocks = {'L1': SimpleNamespace(due=190)} if clocks is None else clocks
    return review_closures(orders, clocks, records, cutoff)


def test_realized_double_signoff_matches_frozen_appointment():
    summary, proof = compare([posted(), posted()])
    assert summary['states'] == {'回执一致': 1}
    assert proof['ticket'] == 'L1-1'
    assert proof['statutory_deadline'] == 190
    assert proof['recorded_after_deadline'] is False
    assert proof['planned']['second'] == '马二审'
    assert proof['findings'] == []


def test_exact_deadline_is_in_time_and_after_deadline_is_flagged_for_reconciliation():
    exact = compare([posted(recorded=190)])[1]
    after = compare([posted(recorded=191)])[1]
    assert not exact['recorded_after_deadline']
    assert after['recorded_after_deadline']
    assert after['findings'] == ['录入时间与逾期标签待核']


def test_only_visible_receipts_are_used_when_checking_shared_numbers():
    late = posted('L2', recorded=211, ticket='L1-1')
    original = compare([posted(), late])
    changed = compare([posted(), late], cutoff=211)
    assert original[0]['reused_numbers'] == []
    assert changed[0]['reused_numbers'] == ['L1-1']
    assert changed[1]['findings'] == ['跨工单结案流水重复']
    assert changed[2]['findings'] == ['跨工单结案流水重复', '无排班记录']


def test_conflicting_receipt_is_quarantined_and_cannot_replace_valid_row():
    first = posted()
    second = posted(recorded=180, ticket='L1-OTHER', signature='另一督查')
    facts = compare([second, first])
    assert facts == compare([first, second])
    assert facts[1]['findings'] == ['同一工单有冲突结案']
    assert facts[1]['tickets'] == ['L1-1', 'L1-OTHER']
    assert 'closure' not in facts[1]


def test_before_finish_supervisor_matches_distinct_issues():
    mark = posted(recorded=153, primary='马二审', signature='马二审')
    findings = compare([mark])[1]['findings']
    assert findings == ['实际首审与排班不符', '同人复签', '回执早于计划完审']


def test_missing_office_calendar_does_not_infer_legal_lateness():
    proof = compare([posted(late=True)], clocks={'L1': SimpleNamespace(due=None)})[1]
    assert proof['recorded_after_deadline'] is None
    assert proof['findings'] == []


def test_permit_pending_and_manual_close_are_visible_in_same_summary():
    pending = Appointment('L2', '主管协调', None, None, None, None, '缺席')
    orders = [pending, scheduled()]
    summary, first, second = compare([posted('L2')], orders)
    assert summary['permits'] == 2 and summary['linked_receipts'] == 1
    assert first['state'] == '截面未结案'
    assert second['findings'] == ['台账无排班但有签审回执']


def test_duplicate_schedule_and_invalid_received_clock_are_rejected():
    with pytest.raises(ValueError, match='重复工单'):
        compare([], [scheduled(), scheduled()])
    with pytest.raises(ValueError, match='早于收件'):
        compare([posted(recorded=102)])
