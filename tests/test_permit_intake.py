import pytest
from permitdesk.permit_intake.inbox import load_permits,route_aliases
from permitdesk.permit_intake.service import intake,material_workload

def form(**changes):
    row=dict(permit="段-33",district="城区",road=" y k4 ",work="应急管线",customer="自来水营运部",received=71,
             opened=70,version=1,obstruction=25,lanes=2,files=["压痕图","围挡图"],urgent=True,withdrawn=False,planned=1600)
    row.update(changes)
    return row

def test_known_version_hard_cutoff():
    # TRAP-42 迟于截面的修订不得进入特征源。
    rows=[form(),form(version=2,received=89,lanes=3)]
    assert load_permits(rows,{},88).active[0].lanes==2
    assert load_permits(rows,{},89).active[0].lanes==3

def test_road_alias_permutation():
    # TRAP-22 道路别名台账顺序不能改变受理主体。
    records={"蓝田街":[" LT31 ","蓝田路"],"苏崖支路":[" yk4"]}
    a=route_aliases(records)
    assert a==route_aliases(dict(reversed(list(records.items()))))
    assert intake([form()],records,500).active[0].road=="苏崖支路"

def test_same_version_conflict_quarantine():
    answers=load_permits([form(),form(lanes=3,received=73)],{},500)
    assert len(answers.active)==0 and answers.log[0]["state"]=="同版冲突"

def test_identical_canonical_content():
    rows=[form(),form(road="YK4",files=["围挡图","压痕图","围挡图"],received=73)]
    got=load_permits(rows,{},350)
    assert len(got.active)==1 and got.active[0].files==("压痕图","围挡图")
    assert got.active[0].received==73

def test_withdrawal_overrides_active():
    rows=[form(),form(version=2,withdrawn=True)]
    got=load_permits(rows,{},1000)
    assert not got.active and got.log[0]["state"]=="已撤回"

def test_explicit_alias_conflict():
    with pytest.raises(ValueError,match="指向"):
        route_aliases({"甲街":["A"],"乙街":["a"]})

def test_impossible_row_isolation():
    rows=[form(),form(permit="错",planned=50),form(permit="文件",files=[False])]
    got=load_permits(rows,{},1000)
    assert len(got.active)==1 and sum(r["state"]=="隔离" for r in got.log)==2

def test_cases_grouped_by_district_and_work():
    rows=[form(),form(permit="F"),form(permit="L",district="湾畔")]
    data=material_workload(load_permits(rows,{},1000))
    assert sorted(row["submitted"] for row in data)==[1,2]
