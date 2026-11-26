from dataclasses import asdict
from .ledger import metric,integrity
from .closure_evidence import review_closures

def review(orders,prediction,traces,controls):
    measurement=metric(prediction,traces,controls["audit_at"])
    receipt,evidence=integrity(orders,controls)
    metadata=asdict(measurement)
    metadata.pop("rows")
    return receipt,[{**receipt,**metadata},*evidence,*measurement.rows]
