from dataclasses import asdict
from .classifier import fit,assess
from .contracts import ModelPolicy
from .forward_validation import walk_forward

def classify_cases(observations,current,definitions):
    model=fit(observations,ModelPolicy.parse(definitions))
    predictions={key:assess(model,row) for key,row in current.items()}
    return model,predictions

def explain(model,predictions):
    shapes=[{"end":bound,"calibrated":round(p,4),"support":n} for bound,p,n in model.buckets]
    results=[dict(asdict(value),permit=key) for key,value in sorted(predictions.items())]
    return shapes+results
