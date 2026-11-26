from dataclasses import asdict
from .staffing import solve
from .shift_replay import shift_impact

def prepare_roster(cases,clocks,predicted,documents,config,capacity):
    return solve(cases,clocks,predicted,documents,config["reviewers"],capacity,config["at"])

def hearing_records(orders):
    return [asdict(summary) for summary in orders]
