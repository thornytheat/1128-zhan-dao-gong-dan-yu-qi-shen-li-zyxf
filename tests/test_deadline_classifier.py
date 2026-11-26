import pytest
from permitdesk.deadline_classifier.classifier import sigmoid,normalize,fit,monotone_bins,assess
from permitdesk.deadline_classifier.contracts import ModelPolicy
from permitdesk.review_features.contracts import ReviewVector,EncodedSamples

def policy(**adjust):
    row=dict(key="N9",ridge=.03,maximum_iterations=80,learning_rate=.2,cut_low=.35,cut_high=.6,reject=6.,low_count=2)
    row.update(adjust)
    return ModelPolicy(**row)

def row(i,truth=None, far=False):
    return ReviewVector(f"P{i}","中央",(12. if far else i%12/10,.6,.5,.1,.4,.3,0.),
                        truth if truth is not None else i%12>6,i*20,i*20+10)

def corpus(default=None): return EncodedSamples(tuple(row(i,default) for i in range(60)),
        tuple(row(i,default) for i in range(60,110)),())

def test_stable_rare_case_logit():
    # TRAP-31 极端负 logit 的指数不能导致溢出。
    assert sigmoid(-1000)==0 and sigmoid(1000)==1
    assert sigmoid(0)==.5 and sigmoid(-4)==pytest.approx(1-sigmoid(4))

def test_fixed_constant_scales():
    # TRAP-32 多列常数不应污染所有归一化结果。
    model=fit(corpus(),policy())
    assert model.spread[1:]==(.08,)*6
    assert normalize(model.center,model.center,model.spread)==(0.,)*7

def test_isotonic_calibration_pooling():
    # TRAP-44 逆序置信桶合并保持保序并检查远离训练域。
    buckets=monotone_bins([(0,1),(4,4),(0,4),(5,5)])
    assert len(buckets)==3 and buckets[1][0]==.75 and buckets[1][2]==8
    assert buckets[1][1]==.5
    estimated=assess(fit(corpus(),policy()),row(20,far=True))
    assert estimated.reliability=="谨慎" and estimated.label=="超出已知工单范围"

def test_scores_change_with_actual_signal():
    fitted=fit(corpus(),policy())
    left=assess(fitted,row(1))
    right=assess(fitted,row(11))
    assert left.raw<right.raw and left.probability<=right.probability
    assert len(right.evidence)==3

def test_all_negative_calibration_does_not_release():
    # TRAP-43 单类历史缺少可验证的逾期召回，推断必须标为谨慎。
    model=fit(corpus(False),policy())
    inspection=assess(model,row(10))
    assert model.labels==0 and inspection.reliability=="谨慎"
    assert 0<=inspection.probability<.5

def test_inference_is_independent_of_batch():
    # TRAP-53 推断批大小不改变已固定统计量。
    model=fit(corpus(),policy())
    target=row(8)
    output=[assess(model,candidate) for candidate in (target,row(9,far=True),target)]
    assert output[0]==output[2]==assess(model,target)

def test_never_train_on_validation_profiles():
    base=corpus()
    changed=EncodedSamples(base.history,tuple(row(i,True,far=True) for i in range(70,110)),())
    a=fit(base,policy())
    c=fit(changed,policy())
    assert a.weights==c.weights and a.center==c.center and a.buckets!=c.buckets

def test_malformed_model_request():
    with pytest.raises(ValueError):
        fit(corpus(),policy(cut_high=.1))
    with pytest.raises(ValueError):
        fit(EncodedSamples((),(),()),policy())
