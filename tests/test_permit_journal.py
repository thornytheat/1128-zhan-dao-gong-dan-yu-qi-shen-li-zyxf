from types import SimpleNamespace as O
import pytest
from permitdesk.permit_journal.ledger import metric,integrity
from permitdesk.review_roster.contracts import Appointment

def trace(key="P",**updates):
    row=dict(permit=key,submitted=75,recorded=420,late=True,signature="封顺平",disposition="退回",primary="张翠",ticket="ADS")
    row.update(updates)
    return row

def scheduled(key="P",**changes):
    row=dict(permit=key,state="安排复核",reviewer="韩",second="陈",start=105,finish=165,reason="")
    row.update(changes)
    return Appointment(**row)

def test_zero_positives_no_average_precision():
    # TRAP-43 无已确认逾期时 AP 明确未定义，空桶具独立计数。
    output=metric({"P":O(probability=.1)},[trace(late=False)],520)
    assert output.average_precision is None and output.pos==0 and output.null_buckets==4
    assert output.avg_brier==pytest.approx(.01)

def test_true_false_tie_changes_average_precision_once():
    docs=[trace(),trace("L",late=False),trace("K")]
    score={"P":O(probability=.9),"L":O(probability=.9),"K":O(probability=.4)}
    output=metric(score,docs,500)
    assert output.average_precision==pytest.approx(((1/2)+(2/3))/2)
    assert metric(score,docs[::-1],500)==output

def test_future_outcome_excluded_from_audit():
    scores={"P":O(probability=.4)}
    assert metric(scores,[trace(recorded=501)],500).observed==0
    assert metric(scores,[trace(recorded=500)],500).observed==1

def test_truth_key_must_be_unique():
    with pytest.raises(ValueError,match="相互矛盾"):
        metric({},[trace(),trace(late=False)],500)

def test_right_edge_probability_bucket():
    result=metric({"P":O(probability=1.)},[trace()],500)
    assert result.rows[4]["n"]==1 and result.rows[4]["realized"]==1
    assert result.avg_brier==0 and result.average_precision==1

def test_tampered_secondary_signature():
    stat,reason=integrity([scheduled(second="韩")],{})
    assert not stat["passed"] and reason[0]["issue"]=="invalid_slot_or_signatures"

def test_assignment_ineligible_state_conflict():
    summary,issues=integrity([scheduled(),scheduled(state="通知补件")],{})
    assert not summary["passed"] and {r["issue"] for r in issues}=={"duplicate","unscheduled_with_reservation"}

def test_source_model_and_calendar_invalidate_receipt():
    # TRAP-54 模型、观察或地区班表变动须生成不同签发摘要。
    case=[scheduled(),scheduled("L")]
    a=integrity(case,{"model":3,"calendar":"v7"})[0]["digest"]
    assert a==integrity(case[::-1],{"calendar":"v7","model":3})[0]["digest"]
    assert a!=integrity(case,{"model":3,"calendar":"v8"})[0]["digest"]
