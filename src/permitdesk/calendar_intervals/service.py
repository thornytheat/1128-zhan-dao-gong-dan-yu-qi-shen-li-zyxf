from dataclasses import asdict
from .business_time import index_calendar,balance
from .clock_receipt import office_projection

def resolve_clocks(permits, calendars, pauses, moment, settings):
    offices=index_calendar(calendars)
    result={}
    for row in permits:
        quota=settings["urgent_minutes"] if row.urgent else settings["ordinary_minutes"]
        result[row.permit]=balance(row.permit,row.opened,moment,quota,offices.get(row.district,()),pauses.get(row.permit,()))
    return result,offices


def clock_records(permits, clocks, offices, pauses, moment):
    records = []
    for case in permits:
        clock = clocks[case.permit]
        evidence = office_projection(clock, case.opened, moment, offices.get(case.district, ()),
                                     pauses.get(case.permit, ()))
        records.append(asdict(clock) | evidence)
    return records
