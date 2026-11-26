from types import SimpleNamespace as O
import pytest
from permitdesk.review_roster.staffing import need_two,window,solve
from permitdesk.review_roster.contracts import Reviewer

def letter(key="P",**edits):
    payload=dict(permit=key,district="锦西",work="给水",lanes=1,urgent=False,obstruction=18)
    payload.update(edits)
    return O(**payload)

def official(name="洪",**edits):
    payload=dict(handle=name,district="锦西",skills=["给水"],available=100,shift_end=280,
                 allow_emergency=True,stock=3,paused=[],second_sign=True)
    payload.update(edits)
    return payload

def run(cases,people,cap=2, missing=None, balances=None):
    by_key={row.permit:O(overdue=False,remaining=20) for row in cases}
    predict={row.permit:O(probability=.5) for row in cases}
    return solve(cases,balances or by_key,predict,missing or {row.permit:() for row in cases},people,cap,105)

def test_emergency_conflict_policy():
    # TRAP-19 应急、真实剩余分钟及概率同时命中时按显式优先级而非输入先后。
    workload=[letter("Z"),letter("P",urgent=True)]
    out=run(workload,[official()],1)
    assert out==run(workload[::-1],[official()],1)
    assert out[0].permit=="P" and out[1].state=="保留待审"

def test_active_duplicate_reviewer():
    with pytest.raises(ValueError,match="重复"):
        run([], [official(),official()])

def test_material_notice_does_not_consume_capacity():
    out=run([letter("D"),letter("M")],[official()],1,missing={"D":["道路占挖告知函"],"M":[]})
    assert [row.state for row in out]==["通知补件","安排复核"]
    assert out[0].reviewer is None

def test_statutory_emergency_can_parallel_documents():
    out=run([letter(urgent=True)],[official(allow_emergency=True)],missing={"P":["图纸"]})
    assert out[0].state=="安排复核" and out[0].reason=="应急先会签，补件并行"
    assert run([letter(urgent=True)],[official(allow_emergency=False)])[0].state=="主管协调"

def test_second_reviewer_independent():
    case=letter(lanes=4)
    assert need_two(case)
    assert run([case],[official()])[0].state=="主管协调"
    outcome=run([case],[official("姚"),official("周")])[0]
    assert outcome.reviewer!=outcome.second and outcome.finish-outcome.start==55

def test_half_open_pause_times():
    m=Reviewer.parse(official(paused=[[130,155],[200,230]]))
    assert window(m,105,25)==(105,130)
    assert window(m,107,25)==(155,180)
    assert window(m,235,46) is None

def test_wrong_district_does_not_serve():
    out=run([letter()],[official(district="景南")])
    assert out[0].state=="主管协调"

def test_shift_and_hard_case_quota():
    out=run([letter("A"),letter("B")],[official(stock=1)])
    assert out[0].start==105 and out[0].finish==130
    assert out[1].state=="主管协调"
