from pathlib import Path
import json
from collections import Counter
from hashlib import sha256
from dataclasses import asdict
from .permit_intake.service import intake,material_workload
from .calendar_intervals.service import clock_records, resolve_clocks
from .review_features.service import build_features,feature_check
from .deadline_classifier.service import classify_cases,explain,walk_forward
from .review_roster.service import prepare_roster,hearing_records,shift_impact
from .permit_journal.service import review,review_closures

SAMPLE=Path(__file__).resolve().parents[2]/"sample_data"

def load(name):
    return json.loads((SAMPLE/name).read_text(encoding="utf-8"))

def run(capacity: int|None=None)->dict:
    cap=8 if capacity is None else capacity
    if type(cap) is not int or not 1<=cap<=100:
        raise ValueError("审理席位配额须在 1 至 100")
    cfg=load("rules_and_rosters.json")
    calendar=load("working_intervals.json")
    cases=intake(load("permit_intake.json"),cfg["road_aliases"],cfg["at"])
    clocks,outlets=resolve_clocks(cases.active,calendar,cfg["pauses"],cfg["at"],cfg)
    old,current,docs=build_features(cases.active,load("historical_decisions.json"),clocks,cfg)
    model,scored=classify_cases(old,current,cfg["model"])
    hearings=prepare_roster(cases.active,clocks,scored,docs,cfg,cap)
    policy_replay=walk_forward(old,model.policy,cfg["at"],review_slots=cap)
    shift_review=shift_impact(cases.active,clocks,scored,docs,cfg["reviewers"],cap,cfg["at"],hearings,cfg["exercise_absences"])
    receipts=load("closure_register.json")
    followup=review_closures(hearings,clocks,receipts,cfg["audit_at"])
    mark=sha256(json.dumps([asdict(model),calendar,cfg["reviewers"],cfg["pauses"],shift_review["replay_id"]],sort_keys=True).encode()).hexdigest()
    check,detail=review(hearings,scored,receipts,
                        {"audit_at":cfg["audit_at"],"analysis_digest":mark,"capacity":cap})
    docket={row.permit:row for row in cases.active}
    result=[]
    for item in hearings:
        source=docket[item.permit]
        holding=clocks[item.permit]
        assessed=scored[item.permit]
        result.append({"permit":item.permit,"district":source.district,"road":source.road,"work":source.work,
                       "remaining":holding.remaining,"due":holding.due,"risk":assessed.probability,
                       "primary":item.reviewer,"secondary":item.second,"state":item.state,
                       "reason":item.reason+" · "+assessed.label})
    counts=Counter(row.state for row in hearings)
    overdue=sum(clock.overdue for clock in clocks.values())
    history=detail[1:]
    values=[{"label":f"{ix*20}–{(ix+1)*20}%", "value":row["n"]} for ix,row in enumerate(history) if "bucket" in row]
    return {
        "metrics":{"有效占道申请":len(cases.active),"已过法定时限":overdue,"已安排复核":counts["安排复核"],
                   "待通知补件":counts["通知补件"]},
        "columns":{"permit":"许可号","district":"辖区","road":"道路","work":"施工类型","remaining":"剩余法定分钟",
                   "due":"截止分钟","risk":"校准逾期概率","primary":"首审","secondary":"二审","state":"处置","reason":"审理依据"},
        "rows":result,"series":values,
        "stages":[{"title":"许可流转","summary":f"{len(cases.active)} 份使用有效修订，保留冲突及撤回记录",
                   "records":[*cases.log,*material_workload(cases)]},
                  {"title":"日历折算","summary":f"工作时钟映射 {len(outlets)} 个街区，标注假期及补正暂停",
                   "records":clock_records(cases.active,clocks,outlets,cfg["pauses"],cfg["at"])},
                  {"title":"审理特征","summary":f"历史训练 {len(old.history)} 宗，留出 {len(old.calibration)} 宗",
                   "records":feature_check(current,docs)},
                  {"title":"超期概率","summary":f"模型 {model.policy.key}，保序校准 {len(model.buckets)} 段及按时点滚动复验",
                   "records":[*explain(model,scored),*policy_replay]},
                  {"title":"审理编组","summary":f"席位配额 {cap}，实际安排 {counts['安排复核']} 宗",
                   "records":[*hearing_records(hearings),shift_review]},
                  {"title":"许可追溯","summary":"回执及双签核对通过" if check["passed"] else "签审凭证冲突",
                   "records":[*detail,*followup]}],
    }
