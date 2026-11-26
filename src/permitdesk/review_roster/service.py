from dataclasses import asdict

from .notice_ledger import NoticeLedger
from .reissue import reissue_roster, reissue_summary
from .shift_replay import SCHEDULED, shift_impact
from .staffing import solve


def prepare_roster(cases, clocks, predicted, documents, config, capacity):
    return solve(cases, clocks, predicted, documents, config["reviewers"], capacity, config["at"])


def baseline_notice_ledger(hearings, issued_minute):
    """已发布班表对应一版首版告知，作为缺班重排不得误删的既有凭据。"""
    ledger = NoticeLedger(issued_minute)
    for order in hearings:
        if order.state == SCHEDULED:
            ledger.record_initial(order.permit, order)
    return ledger


def reissue_shift(cases, clocks, predicted, documents, config, capacity, hearings, absences, ledger=None):
    issued_minute = config["at"]
    return reissue_roster(cases, clocks, predicted, documents, config["reviewers"],
                          capacity, config["at"], hearings, absences, issued_minute, ledger)


def hearing_records(orders):
    return [asdict(summary) for summary in orders]


def reissue_records(result):
    reissued, decisions, ledger, token = result
    summary = reissue_summary(decisions)
    return [{**summary, 'record': '缺班重排裁决', 'replay_token': token},
            *ledger.records(), *decisions]
