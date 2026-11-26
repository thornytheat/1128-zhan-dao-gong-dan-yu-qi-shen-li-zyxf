from collections import defaultdict
from .contracts import Reviewer,Appointment,validate_reviewer

def need_two(case):
    return case.lanes>=3 or case.obstruction>=400

def case_cost(case):
    return 20+case.lanes*5+min(20,case.obstruction//50)

def window(row,cursor,cost):
    begin=max(cursor,row.available)
    for lower,upper in sorted(row.paused):
        if begin+cost<=lower:
            break
        if begin<upper:
            begin=upper
    return (begin,begin+cost) if begin+cost<=row.shift_end else None

def pending_order(case,clock,risk):
    return (not case.urgent,not clock.overdue,clock.remaining,-risk.probability,case.permit)

def eligible_people(case,people,used):
    return [person for person in people
            if person.district==case.district and case.work in person.skills
            and (not case.urgent or person.allow_emergency)
            and used[person.handle]<person.stock]

def slot_combinations(case,people,cursors,used):
    """所有满足辖区、资质、休息、班次和双签约束的班内候选时段。"""
    options=eligible_people(case,people,used)
    cost=case_cost(case)
    combinations=[]
    for person in options:
        first=window(person,cursors[person.handle],cost)
        if not first:
            continue
        if not need_two(case):
            combinations.append((first[1],first[0],person.handle,None,first[1],None))
            continue
        for fellow in options:
            if fellow.handle==person.handle or not fellow.second_sign:
                continue
            second=window(fellow,max(cursors[fellow.handle],first[1]),15)
            if second:
                combinations.append((second[1],first[0],person.handle,fellow.handle,first[1],second[0]))
    return combinations

def parse_roster(roster):
    people=tuple(Reviewer.parse(row) for row in roster)
    if len({row.handle for row in people})!=len(people):
        raise ValueError("审理员重复列入班表")
    for member in people:
        validate_reviewer(member)
    return people

def solve(permits,clocks,scores,missing,roster,limit,asof):
    if not 1<=limit<=100:
        raise ValueError("审理席位配额须在 1 至 100")
    people=parse_roster(roster)
    next_at={item.handle:asof for item in people}
    used=defaultdict(int)
    outcome=[]
    scheduled=0
    for case in sorted(permits,key=lambda item:pending_order(item,clocks[item.permit],scores[item.permit])):
        order=case.permit
        if missing[order] and not case.urgent:
            outcome.append(hold(order,"通知补件","材料仍缺："+"、".join(missing[order])))
            continue
        if scheduled>=limit:
            outcome.append(hold(order,"保留待审","本截面席位配额已用完"))
            continue
        combinations=slot_combinations(case,people,next_at,used)
        if not combinations:
            outcome.append(hold(order,"主管协调","班表内没有符合辖区资质和签审人数的组合"))
            continue
        end,start,primary,secondary,primary_end,secondary_start=min(combinations)
        next_at[primary]=primary_end
        used[primary]+=1
        if secondary is not None:
            next_at[secondary]=end
            used[secondary]+=1
        note="应急先会签，补件并行" if missing[order] else "资质及班内时段可用"
        outcome.append(Appointment(order,"安排复核",primary,secondary,start,end,note))
        scheduled+=1
    return tuple(outcome)

def hold(key,label,reason):
    return Appointment(key,label,None,None,None,None,reason)
