"""Reconcile submitted closure receipts with the frozen dispatch and legal clock."""

from collections import Counter, defaultdict
from dataclasses import asdict

from .contracts import Closure


NO_DISPATCH = '无排班记录'
NOT_CLOSED = '截面未结案'


def index_receipts(raw, cutoff):
    by_permit = defaultdict(set)
    number_index = defaultdict(set)
    for entry in raw:
        row = Closure.parse(entry)
        if row.recorded > cutoff:
            continue
        if row.recorded < row.submitted:
            raise ValueError('结案录入时间早于收件')
        by_permit[row.permit].add(row)
        number_index[row.ticket].add(row.permit)
    shared = {ticket for ticket, owners in number_index.items() if len(owners) > 1}
    return by_permit, shared


def signer_findings(closure, appointment):
    if appointment.state != '安排复核':
        return ['台账无排班但有签审回执']
    findings = []
    if closure.primary != appointment.reviewer:
        findings.append('实际首审与排班不符')
    if closure.primary == closure.signature:
        findings.append('同人复签')
    elif appointment.second is not None and closure.signature != appointment.second:
        findings.append('实际二审与排班不符')
    return findings


def compare_receipt(closure, dispatch, clocks, shared):
    appointment = dispatch.get(closure.permit)
    clock = clocks.get(closure.permit)
    findings = []
    if closure.ticket in shared:
        findings.append('跨工单结案流水重复')
    if appointment is None:
        findings.append(NO_DISPATCH)
    else:
        findings.extend(signer_findings(closure, appointment))
        if appointment.finish is not None and closure.recorded < appointment.finish:
            findings.append('回执早于计划完审')
    if clock is None or clock.due is None:
        modeled_late = None
    else:
        modeled_late = closure.recorded > clock.due
        if modeled_late != closure.late:
            findings.append('录入时间与逾期标签待核')
    return {
        'permit': closure.permit,
        'record': '结案回执校对',
        'state': '待督办复查' if findings else '回执一致',
        'ticket': closure.ticket,
        'closure': asdict(closure),
        'planned': asdict(appointment) if appointment else None,
        'statutory_deadline': clock.due if clock else None,
        'recorded_after_deadline': modeled_late,
        'findings': findings,
    }


def review_closures(orders, clocks, raw, cutoff):
    by_permit, shared = index_receipts(raw, cutoff)
    dispatch = {entry.permit: entry for entry in orders}
    if len(dispatch) != len(orders):
        raise ValueError('排班中有重复工单')
    details = []
    for permit in sorted(set(by_permit) | set(dispatch)):
        receipts = by_permit.get(permit, set())
        if len(receipts) > 1:
            details.append({'permit': permit, 'record': '结案回执校对', 'state': '待督办复查',
                            'findings': ['同一工单有冲突结案'], 'tickets': sorted({row.ticket for row in receipts})})
        elif not receipts:
            details.append({'permit': permit, 'record': '结案回执校对', 'state': NOT_CLOSED, 'findings': []})
        else:
            details.append(compare_receipt(next(iter(receipts)), dispatch, clocks, shared))
    counts = Counter(row['state'] for row in details)
    patterns = Counter(issue for row in details for issue in row['findings'])
    summary = {'record': '结案督办汇总', 'audit_minute': cutoff, 'permits': len(details),
               'states': dict(sorted(counts.items())), 'findings': dict(sorted(patterns.items())),
               'linked_receipts': sum(permit in dispatch for permit in by_permit), 'reused_numbers': sorted(shared)}
    return [summary, *details]
