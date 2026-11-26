from collections import defaultdict
from dataclasses import asdict
from hashlib import sha256
from json import dumps
from math import fsum
from .contracts import Closure,HoldoutReport

def metric(estimate,raw,asof):
    verified={}
    for source in raw:
        closed=Closure.parse(source)
        if closed.recorded<closed.submitted:
            raise ValueError("结案录入时间早于收件")
        if closed.recorded>asof:
            continue
        if closed.permit in verified and verified[closed.permit]!=closed:
            raise ValueError("同一许可有相互矛盾的结案")
        verified[closed.permit]=closed
    matched=[(estimate[key].probability,bool(item.late),key) for key,item in verified.items() if key in estimate]
    levels=defaultdict(list)
    for score,truth,key in matched:
        levels[score].append(truth)
    pos=sum(outcome for _,outcome,_ in matched)
    positives=0
    found=0
    ap=0.
    for _,labels in sorted(levels.items(),reverse=True):
        realized=sum(labels)
        positives+=realized
        found+=len(labels)
        ap+=realized*(positives/found)
    buckets=[[] for _ in range(5)]
    for score,truth,_ in matched:
        buckets[min(4,int(score*5))].append((score,truth))
    rows=[]
    for idx,group in enumerate(buckets):
        average=lambda k: fsum(row[k] for row in group)/len(group) if group else None
        rows.append({"bucket":idx,"n":len(group),"calibrated":average(0),"realized":average(1)})
    brier=fsum((score-truth)**2 for score,truth,_ in matched)/len(matched) if matched else None
    return HoldoutReport(len(verified),len(matched),pos,brier,ap/pos if pos else None,
                         sum(not group for group in buckets),tuple(rows))

def integrity(orders,config):
    seen=set()
    problems=[]
    for row in orders:
        if row.permit in seen:
            problems.append({"permit":row.permit,"issue":"duplicate"})
        seen.add(row.permit)
        if row.state=="安排复核":
            if not row.reviewer or row.second==row.reviewer or row.start is None or row.finish is None or row.start>=row.finish:
                problems.append({"permit":row.permit,"issue":"invalid_slot_or_signatures"})
        elif any(entry is not None for entry in (row.reviewer,row.second,row.start,row.finish)):
            problems.append({"permit":row.permit,"issue":"unscheduled_with_reservation"})
    payload=[config,[asdict(order) for order in sorted(orders,key=lambda x:x.permit)]]
    digest=sha256(dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return {"passed":not problems,"digest":digest},tuple(problems)
