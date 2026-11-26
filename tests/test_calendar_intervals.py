import pytest
from permitdesk.calendar_intervals.business_time import balance,index_calendar,normalize,subtract,portions

def block(start=100,end=200,**edits):
    values=dict(district="南县",start=start,end=end,work=True,closure=False,team="审批一班",authority="市级通知",revision=1)
    values.update(edits)
    return values

def test_weekend_and_pause_excluded():
    case=balance("H",100,440,150,[(100,180),(280,500)],[(290,325)])
    assert case.elapsed==205 and case.paused==35
    assert case.due==385 and case.remaining==-55 and case.overdue

def test_half_open_boundaries():
    # TRAP-23 工作时钟只算左闭右开，暂停端点不能重复抵扣。
    assert portions([(100,200)],200,205)==0
    entry=balance("T",100,200,100,[(100,200),(200,260)],[])
    assert entry.due==200 and entry.remaining==0 and not entry.overdue

def test_version_conflict_and_effective_closure():
    # TRAP-25 同修订日历冲突必须回到人工修正。
    with pytest.raises(ValueError,match="日历版本"):
        index_calendar([block(),block(closure=True)])
    updated=index_calendar([block(),block(145,170,closure=True,revision=2)])
    assert updated["南县"]==((100,145),(170,200))

def test_merged_pause_not_double_counted():
    case=balance("U",100,200,59,[(100,230)],[(125,157),(141,180)])
    assert case.paused==55 and case.elapsed==45
    assert case.due==214 and not case.overdue

def test_clock_skips_future_when_eta_impossible():
    assert balance("K",100,100,90,[(100,161)],()).due is None
    assert balance("K",100,100,60,[(100,170)],()).due==160

def test_every_holiday_windows_independent():
    saved=index_calendar([block(),block(140,161,work=False),block(140,161,work=True,district="西岸")])
    assert saved["南县"]==((100,140),(161,200))
    assert saved["西岸"]==((140,161),)

def test_subtract_nested_stops():
    assert subtract(((100,180),(190,280)),((80,140),(145,240)))==((140,145),(240,280))
    assert normalize([(140,180),(100,145)])==((100,180),)

def test_malformed_markers_raise():
    with pytest.raises(ValueError,match="日历区间"):
        normalize([(19,16)])
    with pytest.raises(ValueError,match="时钟"):
        balance("D",10,1,50,(),())
