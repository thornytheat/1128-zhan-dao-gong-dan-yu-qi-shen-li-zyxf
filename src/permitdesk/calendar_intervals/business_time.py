from collections import defaultdict
from .contracts import OfficeWindow,TimeAccount

def portions(intervals,begin,finish):
    return sum(max(0,min(stop,finish)-max(start,begin)) for start,stop in intervals)

def normalize(intervals):
    merged=[]
    for start,end in sorted(map(tuple,intervals)):
        if end<=start:
            raise ValueError("日历区间不合法")
        if merged and merged[-1][1]>=start:
            merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:
            merged.append((start,end))
    return tuple(merged)

def intersect(first,second):
    return tuple((max(a,c),min(b,d)) for a,b in first for c,d in second if a<d and c<b)

def subtract(intervals, stops):
    output=[]
    for start,end in intervals:
        at=start
        for f,t in stops:
            if f>=end:
                break
            if t<=at:
                continue
            if f>at:
                output.append((at,min(f,end)))
            at=max(at,t)
        if at<end:
            output.append((at,end))
    return tuple(output)

def index_calendar(raw):
    versions=defaultdict(list)
    for data in raw:
        row=OfficeWindow.parse(data)
        if row.end<=row.start:
            raise ValueError("班表时钟倒序")
        versions[(row.district,row.start,row.end)].append(row)
    open_days=defaultdict(list)
    closures=defaultdict(list)
    for (district,start,end),items in versions.items():
        maximum=max(row.revision for row in items)
        states={(v.work,v.closure) for v in items if v.revision==maximum}
        if len(states)>1:
            raise ValueError("有冲突的审批日历版本")
        work,holiday=next(iter(states))
        (open_days if work and not holiday else closures)[district].append((start,end))
    return {zone:subtract(normalize(complete),normalize(closures[zone])) for zone,complete in open_days.items()}

def balance(permit, opened, asof, minutes, office, paused):
    if asof<opened or minutes<=0:
        raise ValueError("许可计时时钟无效")
    office=normalize(office)
    pauses=normalize(paused)
    active=subtract(office,pauses)
    elapsed=portions(active,opened,asof)
    paused_minutes=portions(intersect(office,pauses),opened,asof)
    count=minutes
    due=None
    for begin,end in active:
        start=max(begin,opened)
        if end<=start:
            continue
        if end-start>=count:
            due=start+count
            break
        count-=end-start
    return TimeAccount(permit,elapsed,paused_minutes,minutes,minutes-elapsed,due,elapsed>minutes)
