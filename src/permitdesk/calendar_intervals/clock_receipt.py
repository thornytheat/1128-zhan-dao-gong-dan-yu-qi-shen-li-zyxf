"""Provide the counted and suspended minute ledger for a statutory deadline."""

from .business_time import intersect, normalize, portions, subtract


def clip(intervals, begin, end):
    if begin >= end:
        return ()
    return tuple((max(start, begin), min(stop, end)) for start, stop in intervals if start < end and stop > begin)


def label_elapsed_segments(office, paused, opened, as_of):
    elapsed = clip(office, opened, as_of)
    suspended = intersect(elapsed, paused)
    counted = subtract(elapsed, suspended)
    closed = subtract(((opened, as_of),), elapsed) if opened < as_of else ()
    labeled = []
    for name, intervals in (('计入时限', counted), ('补正暂停', suspended), ('窗口停办', closed)):
        labeled.extend({'start_minute': begin, 'end_minute': end, 'state': name, 'minutes': end - begin}
                       for begin, end in intervals)
    return sorted(labeled, key=lambda row: row['start_minute'])


def remaining_path(active, as_of, remaining):
    route = []
    balance = remaining
    if balance == 0:
        return route, 0
    for start, end in active:
        begin = max(as_of, start)
        if begin >= end:
            continue
        spent = min(end - begin, balance)
        route.append({'from_minute': begin, 'until_minute': begin + spent, 'charge_minutes': spent,
                      'remaining_before': balance, 'remaining_after': balance - spent})
        balance -= spent
        if balance == 0:
            break
    return route, balance


def clock_state(account, balance):
    if account.overdue:
        return '已超时'
    if account.remaining == 0:
        return '已到期'
    if balance:
        return '日历覆盖不足'
    return '尚可审理'


def office_projection(account, opened, as_of, office, pauses):
    if opened > as_of:
        raise ValueError('审理截面早于收件时间')
    windows = normalize(office)
    paused = normalize(pauses)
    active = subtract(windows, paused)
    partitions = label_elapsed_segments(windows, paused, opened, as_of)
    totals = {state: 0 for state in ('计入时限', '补正暂停', '窗口停办')}
    for period in partitions:
        totals[period['state']] += period['minutes']
    if sum(totals.values()) != as_of - opened:
        raise ValueError('时钟分段未覆盖完整审理区间')
    if totals['计入时限'] != account.elapsed or totals['补正暂停'] != account.paused:
        raise ValueError('时钟证据与法定分钟不一致')
    projected, unmet = remaining_path(active, as_of, max(0, account.remaining))
    projected_deadline = projected[-1]['until_minute'] if projected and unmet == 0 else None
    if account.remaining > 0 and projected_deadline != account.due:
        raise ValueError('剩余法定分钟与截止时刻不一致')
    return {
        'permit': account.permit,
        'state': clock_state(account, unmet),
        'elapsed_wall_minutes': as_of - opened,
        'charged_minutes': totals['计入时限'],
        'closed_minutes': totals['窗口停办'],
        'paused_in_office_minutes': totals['补正暂停'],
        'pause_outside_office_minutes': portions(paused, opened, as_of) - totals['补正暂停'],
        'remaining_statutory_minutes': account.remaining,
        'deadline': account.due,
        'timeline': partitions,
        'future_charges': projected,
        'uncovered_future_minutes': unmet,
    }
