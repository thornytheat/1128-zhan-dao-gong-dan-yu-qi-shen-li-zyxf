from collections import Counter, defaultdict
from math import log1p
from .contracts import CaseObservation,ReviewVector,EncodedSamples

def vector(elapsed,allowed,length,lanes,missing,pending,road_class,urgent):
    road_weight={"主干路":1.,"次干路":.6,"支路":.25,"乡道":.1}.get(road_class,.4)
    return (min(2.,elapsed/allowed),log1p(length)/5,lanes/4,missing/6,log1p(pending)/3,road_weight,float(urgent))

def historical_rows(rows, split, now):
    if split>now:
        raise ValueError("特征结案截面晚于回放时间")
    available=[]
    pending=[]
    identities=set()
    for raw in rows:
        row=CaseObservation.parse(raw)
        if row.closed<row.recorded:
            raise ValueError("结果记录早于工单观察截点")
        if row.closed>=now:
            pending.append(row.key)
            continue
        if row.key in identities:
            raise ValueError("同一工单只能纳入一条观察截面")
        identities.add(row.key)
        values=vector(row.elapsed,row.allowed,row.length,row.lanes,row.missing,row.anticipated,row.road_class,row.urgent)
        available.append(ReviewVector(row.key,row.district,values,row.late,row.recorded,row.closed))
    historical=[]
    calibration=[]
    for row in sorted(available,key=lambda x:(x.settled,x.key)):
        play=historical if row.settled<split else calibration
        play.append(row)
    return EncodedSamples(tuple(historical),tuple(calibration),tuple(sorted(pending)))

def predict_rows(permits,clock,names,set_needed,asof):
    queues=Counter(row.district for row in permits)
    vectors={}
    pending={}
    for case in permits:
        due=clock[case.permit]
        required=set(set_needed.get(case.work,set_needed.get("其他",())))
        rest=tuple(sorted(required-set(case.files)))
        fixed=vector(due.elapsed,due.allowed,case.obstruction,case.lanes,len(rest),queues[case.district]-1,
                     names.get(case.road,"其他"),case.urgent)
        vectors[case.permit]=ReviewVector(case.permit,case.district,fixed,None,asof,None)
        pending[case.permit]=rest
    return vectors,pending
