"""告知凭据台账的只追加与内容寻址测试。"""

import pytest

from permitdesk.review_roster.contracts import Appointment
from permitdesk.review_roster.notice_ledger import (
    BACKFILL_KIND,
    INITIAL_KIND,
    REASSIGN_KIND,
    NoticeLedger,
)


def slot(handle='甲', second=None):
    return Appointment('SC-1', '安排复核', handle, second, 100, 125, '资质及班内时段可用')


def test_initial_notice_is_content_addressed_and_append_only():
    ledger = NoticeLedger(90)
    notice = ledger.record_initial('SC-1', slot())
    assert notice.kind == INITIAL_KIND and notice.supersedes is None
    with pytest.raises(ValueError, match='首版告知已存在'):
        ledger.record_initial('SC-1', slot('乙'))
    # 重复首版被拒绝，台账仍只有一张凭据。
    assert [entry.notice_id for entry in ledger.entries] == [notice.notice_id]


def test_reassignment_keeps_old_receipt_and_links_chain():
    ledger = NoticeLedger(90)
    first = ledger.record_initial('SC-1', slot('甲'))
    second = ledger.record_reassignment('SC-1', slot('乙'), first, '缺班改派')
    assert second.kind == REASSIGN_KIND and second.supersedes == first.notice_id
    assert [entry.notice_id for entry in ledger.entries] == [first.notice_id, second.notice_id]
    assert ledger.latest('SC-1').notice_id == second.notice_id


def test_reassignment_requires_existing_previous_notice():
    ledger = NoticeLedger(90)
    with pytest.raises(ValueError, match='原告知凭据'):
        ledger.record_reassignment('SC-1', slot('乙'), None, '缺班改派')


def test_identical_notice_payload_dedupicates_on_rerun():
    ledger = NoticeLedger(90)
    first = ledger.record_initial('SC-1', slot('甲'))
    notice, created = ledger._add(REASSIGN_KIND, 'SC-1', slot('乙'), first.notice_id, '缺班改派')
    assert created is True
    again, created_again = ledger._add(REASSIGN_KIND, 'SC-1', slot('乙'), first.notice_id, '缺班改派')
    assert created_again is False and again.notice_id == notice.notice_id
    assert len(ledger.entries) == 2


def test_backfill_notice_has_no_superseded_chain():
    ledger = NoticeLedger(90)
    notice = ledger.record_backfill('SC-9', slot('丙'), '释放席位补位')
    assert notice.kind == BACKFILL_KIND and notice.supersedes is None


def test_invalid_issued_clock_rejected():
    with pytest.raises(ValueError, match='告知时钟'):
        NoticeLedger(-1)


def test_chain_reports_full_history_per_permit():
    ledger = NoticeLedger(90)
    first = ledger.record_initial('SC-1', slot('甲'))
    second = ledger.record_reassignment('SC-1', slot('乙'), first, '缺班改派')
    ledger.record_backfill('SC-2', slot('丙'), '释放席位补位')
    assert ledger.chain() == {
        'SC-1': [first.notice_id, second.notice_id],
        'SC-2': [ledger.latest('SC-2').notice_id],
    }
