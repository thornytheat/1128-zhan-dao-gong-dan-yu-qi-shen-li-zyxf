from math import exp,fsum,sqrt
from dataclasses import replace
from .contracts import Model,RiskNote

def sigmoid(x):
    if x>=0:
        return 1/(1+exp(-x))
    t=exp(x)
    return t/(1+t)

def normalize(x,mid,spread):
    return tuple((value-center)/std for value,center,std in zip(x,mid,spread,strict=True))

def logit(model,features):
    n=normalize(features,model.center,model.spread)
    return model.weights[0]+fsum(w*x for w,x in zip(model.weights[1:],n,strict=True))

def monotone_bins(values):
    blocks=[]
    for ix,(positives,n) in enumerate(values):
        guess=(ix+.5)/len(values)
        blocks.append([ix,ix,(positives+guess)*1.,(n+1)*1.,n])
        while len(blocks)>=2 and blocks[-2][2]/blocks[-2][3]>blocks[-1][2]/blocks[-1][3]:
            a,b=blocks[-2:]
            blocks[-2:]=[[a[0],b[1],a[2]+b[2],a[3]+b[3],a[4]+b[4]]]
    return tuple(((high+1)/len(values),p/n,known) for _,high,p,n,known in blocks)

def fit(samples,policy):
    if policy.cut_low>policy.cut_high:
        raise ValueError("审理评分阈值反向")
    profiles=samples.history
    if not profiles or any(row.outcome is None for row in (*profiles,*samples.calibration)):
        raise ValueError("缺少已结案训练标签")
    positives=sum(row.outcome for row in profiles)
    cols=tuple(zip(*(row.values for row in profiles),strict=True))
    count=len(profiles)
    centers=tuple(fsum(values)/count for values in cols)
    dispersions=tuple(max(.08,sqrt(fsum((v-c)**2 for v in col)/count)) for c,col in zip(centers,cols,strict=True))
    vector_set=[((1.,*normalize(row.values,centers,dispersions)), int(row.outcome)) for row in profiles]
    important=max(1.,min(8.,(count-positives)/max(1,positives)))
    betas=[0.]*(len(cols)+1)
    for _ in range(policy.maximum_iterations):
        grad=[0.] * len(betas)
        weight_total=0.
        for vector,truth in vector_set:
            importance=important if truth else 1
            error=importance*(sigmoid(fsum(w*x for w,x in zip(betas,vector,strict=True)))-truth)
            weight_total+=importance
            for j,x in enumerate(vector):
                grad[j]+=error*x
        change=0.
        for j,g in enumerate(grad):
            increment=policy.learning_rate*(g/weight_total+(betas[j]*policy.ridge if j else 0))
            betas[j]-=increment
            change=max(change,abs(increment))
        if change<1e-7:
            break
    fitted=Model(policy,tuple(betas),centers,dispersions,(),positives,count)
    hist=[[0,0] for _ in range(8)]
    for row in samples.calibration:
        p=sigmoid(logit(fitted,row.values))
        cell=hist[min(7,int(p*8))]
        cell[0]+=row.outcome
        cell[1]+=1
    return replace(fitted,buckets=monotone_bins(hist))

def assess(model,record):
    raw=sigmoid(logit(model,record.values))
    _,guess,support=next(item for item in model.buckets if raw<=item[0])
    normalized=normalize(record.values,model.center,model.spread)
    in_domain=max(abs(x) for x in normalized)<=model.policy.reject
    reliability="正常" if in_domain and support>=model.policy.low_count and 0<model.labels<model.train else "谨慎"
    if not in_domain:
        label="超出已知工单范围"
    elif reliability!="正常":
        label="校准样本偏少"
    elif guess>=model.policy.cut_high:
        label="高逾期风险"
    elif guess>=model.policy.cut_low:
        label="待关注"
    else:
        label="低风险"
    influence=tuple(sorted(range(len(normalized)),key=lambda ix:(-abs(model.weights[ix+1]*normalized[ix]),ix))[:3])
    return RiskNote(round(guess,5),round(raw,5),reliability,label,influence)
