from math import log1p
import pytest
from permitdesk.review_features.snapshot import vector,historical_rows,predict_rows
from types import SimpleNamespace

def signature(i,**extra):
    row=dict(key=f"M{i}",district="城区",road_class="主干路",work="排水",elapsed=60+i*6,allowed=360,
             length=23,lanes=2,missing=0,anticipated=3,urgent=False,recorded=i*13,closed=i*13+20,late=bool(i%2))
    row.update(extra)
    return row

def form(key,zone,**fields):
    row=dict(permit=key,district=zone,work="排水",files=("围挡图",),obstruction=21,lanes=1,road="东一街",urgent=False)
    row.update(fields)
    return SimpleNamespace(**row)

def test_closed_label_never_used_early():
    # TRAP-42 结案标签只能在发生并入账之后使用。
    rows=[signature(0),signature(2),signature(4)]
    fit=historical_rows(rows,44,65)
    assert [p.key for p in fit.history]==["M0"]
    assert [p.key for p in fit.calibration]==["M2"]
    assert fit.held_back==("M4",)

def test_normalization_business_units():
    fields=vector(360,360,20,2,3,9,"次干路",False)
    assert fields==pytest.approx((1,log1p(20)/5,.5,.5,log1p(9)/3,.6,0))

def test_elapsed_feature_saturated():
    assert vector(1500,100,20,2,0,0,"其他",True)[0]==2
    assert vector(0,100,20,2,0,0,"乡道",False)[0]==0

def test_count_never_mixes_districts():
    rows=[form("A","区甲"),form("B","区甲"),form("C","区乙")]
    clocks={p.permit:SimpleNamespace(elapsed=50,allowed=130) for p in rows}
    vec,missing=predict_rows(rows,clocks,{"东一街":"次干路"},{"排水":["围挡图","告知函"]},200)
    assert vec["A"].values[4]==pytest.approx(log1p(1)/3)
    assert vec["C"].values[4]==0 and missing["C"]==("告知函",)

def test_calendar_deadline_only_records_past():
    save=historical_rows([signature(0),signature(2)],20,46)
    assert len(save.history)==0 and len(save.calibration)==1 and save.held_back==("M2",)

def test_duplicate_case_sample_refused():
    with pytest.raises(ValueError,match="一条观察"):
        historical_rows([signature(0),signature(0)],40,50)

def test_invalid_data_clocks_refused():
    with pytest.raises(ValueError,match="早于"):
        historical_rows([signature(4,closed=30)],70,120)
    with pytest.raises(ValueError,match="晚于"):
        historical_rows([],100,90)

def test_outcome_never_in_live_inference_vector():
    rows=[form("A","区甲")]
    assigned,notes=predict_rows(rows,{"A":SimpleNamespace(elapsed=10,allowed=90)}, {}, {"其他":["巡视记录"]},120)
    assert assigned["A"].outcome is None and assigned["A"].settled is None
    assert notes["A"]==("巡视记录",)
