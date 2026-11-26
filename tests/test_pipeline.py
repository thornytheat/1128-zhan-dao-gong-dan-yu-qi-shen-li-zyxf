import json
import pytest
from permitdesk.pipeline import run

def test_permit_full_result():
    packet=run()
    assert packet==run()
    assert len(packet["rows"])>=15 and len(packet["series"])==5 and len(packet["stages"])==6
    assert packet["stages"][-1]["records"][0]["passed"]
    json.dumps(packet,allow_nan=False)

def test_queue_capacity_and_material_decisions():
    smallest=run(1)
    ample=run(15)
    assert smallest["metrics"]["已安排复核"]==1
    assert ample["metrics"]["已安排复核"]>1
    assert smallest["stages"][-1]["records"][0]["digest"]!=ample["stages"][-1]["records"][0]["digest"]
    assert any(row["state"]=="通知补件" for row in ample["rows"])

def test_invalid_form_disposition_visible():
    entries=run()["stages"][0]["records"]
    assert {"同版冲突","已撤回","隔离","迟到更新"}<={record.get("state") for record in entries}

def test_bucket_sizes_match_observed_closure_volume():
    packet=run()
    audit=packet["stages"][-1]["records"][0]
    assert sum(point["value"] for point in packet["series"])==audit["observed"]
    assert audit["observed"]>0

def test_invalid_capacity_never_enters_scoring():
    for option in (0,101,False,"2"):
        with pytest.raises(ValueError,match="配额"): run(option)
