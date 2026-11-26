from collections import defaultdict
from dataclasses import replace
from .contracts import PermitUpdate,Intake,validate_dates

def load_permits(updates, canonical, now):
    registered=defaultdict(list)
    events=[]
    for raw in updates:
        try:
            row=PermitUpdate.parse(raw)
            validate_dates(row)
        except ValueError as error:
            events.append({"permit":raw.get("permit","未知申请"),"state":"隔离","reason":str(error)})
            continue
        if row.received>now:
            events.append({"permit":row.permit,"state":"迟到更新","seen":row.received})
            continue
        key=row.road.replace(" ","").upper()
        materials=tuple(sorted({item.strip() for item in row.files}))
        registered[row.permit].append(replace(row,road=canonical.get(key,key),files=materials))
    priority=[]
    for permit, values in sorted(registered.items()):
        version=max(item.version for item in values)
        versions=[item for item in values if item.version==version]
        # The form arrival timestamp is transport metadata, not a field conflict.
        identity={replace(row,received=row.opened) for row in versions}
        if len(identity)>1:
            events.append({"permit":permit,"state":"同版冲突","version":version})
            continue
        head=max(versions,key=lambda row:row.received)
        if head.withdrawn:
            status="已撤回"
        else:
            status="已受理"
            priority.append(head)
        events.append({"permit":permit,"state":status,"version":version,"road":head.road})
    observations=sorted(events,key=lambda row:(row["permit"],row["state"],str(row)))
    return Intake(tuple(priority),tuple(observations))

def route_aliases(data):
    destinations={}
    for route,aliases in sorted(data.items()):
        for name in (*aliases,route):
            cleaned=name.replace(" ","").upper()
            previous=destinations.get(cleaned)
            if previous is not None and previous!=route:
                raise ValueError("道路别名指向了多个标准道路")
            destinations[cleaned]=route
    return destinations
