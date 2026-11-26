from collections import Counter
from .inbox import load_permits,route_aliases

def intake(updates,names,now):
    return load_permits(updates,route_aliases(names),now)

def material_workload(register):
    counts=Counter((row.district,row.work) for row in register.active)
    return [{"district":district,"type":work,"submitted":count} for (district,work),count in sorted(counts.items())]
