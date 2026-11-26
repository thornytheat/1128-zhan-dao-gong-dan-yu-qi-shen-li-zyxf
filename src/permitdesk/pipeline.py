from pathlib import Path
import json
from collections import Counter
from hashlib import sha256
from dataclasses import asdict
from .permit_intake.service import intake,material_workload
from .calendar_intervals.service import clock_records, resolve_clocks
from .review_features.service import build_features,feature_check
from .deadline_classifier.service import classify_cases,explain,walk_forward
from .review_roster.service import (
    prepare_roster,
    hearing_records,
    shift_impact,
    baseline_notice_ledger,
    reissue_shift,
    reissue_records,
)
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
    notice_ledger=baseline_notice_ledger(hearings,cfg["at"])
    policy_replay=walk_forward(old,model.policy,cfg["at"],review_slots=cap)
    shift_review=shift_impact(cases.active,clocks,scored,docs,cfg["reviewers"],cap,cfg["at"],hearings,cfg["exercise_absences"])
    reissue_result=reissue_shift(cases.active,clocks,scored,docs,cfg,cap,hearings,
                                 cfg["exercise_absences"],notice_ledger)
    reissued,decisions,notice_journal,reissue_token=reissue_result
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
        "reissue":build_reissue_packet(reissue_result,cfg["exercise_absences"]),
        "stages":[{"title":"许可流转","summary":f"{len(cases.active)} 份使用有效修订，保留冲突及撤回记录",
                   "records":[*cases.log,*material_workload(cases)]},
                  {"title":"日历折算","summary":f"工作时钟映射 {len(outlets)} 个街区，标注假期及补正暂停",
                   "records":clock_records(cases.active,clocks,outlets,cfg["pauses"],cfg["at"])},
                  {"title":"审理特征","summary":f"历史训练 {len(old.history)} 宗，留出 {len(old.calibration)} 宗",
                   "records":feature_check(current,docs)},
                  {"title":"超期概率","summary":f"模型 {model.policy.key}，保序校准 {len(model.buckets)} 段及按时点滚动复验",
                   "records":[*explain(model,scored),*policy_replay]},
                  {"title":"审理编组","summary":f"席位配额 {cap}，实际安排 {counts['安排复核']} 宗；缺班重排裁决 {len(decisions)} 单",
                   "records":[*hearing_records(hearings),shift_review,
                              {'record':'缺班重排告知台账','notices':len(notice_journal.entries),
                               'replay_token':reissue_token},
                              *reissue_records(reissue_result)]},
                  {"title":"许可追溯","summary":"回执及双签核对通过" if check["passed"] else "签审凭证冲突",
                   "records":[*detail,*followup]}],
    }


def prepare_inputs(capacity):
    """加载样例并产出重排所需的全部截面输入（含基线班表与首版告知台账）。"""
    cfg=load("rules_and_rosters.json")
    calendar=load("working_intervals.json")
    cases=intake(load("permit_intake.json"),cfg["road_aliases"],cfg["at"])
    clocks,outlets=resolve_clocks(cases.active,calendar,cfg["pauses"],cfg["at"],cfg)
    old,current,docs=build_features(cases.active,load("historical_decisions.json"),clocks,cfg)
    _model,scored=classify_cases(old,current,cfg["model"])
    hearings=prepare_roster(cases.active,clocks,scored,docs,cfg,capacity)
    ledger=baseline_notice_ledger(hearings,cfg["at"])
    return cfg,cases,clocks,scored,docs,hearings,ledger


def build_reissue_packet(reissue_result, absences):
    reissued,decisions,ledger,token=reissue_result
    from .review_roster.reissue import reissue_summary
    return {
        "record":"缺班重排复核安排",
        "replay_token":token,
        "absence_minutes":{handle:list(span) for handle,span in sorted(absences.items())},
        "summary":reissue_summary(decisions),
        "notices":ledger.records(),
        "notice_chains":ledger.chain(),
        "decisions":decisions,
        "appointments":[asdict(row) for row in reissued],
    }


def reissue_scenario(capacity, absences):
    """面向工作台的缺班重排：校验缺班输入后重出本班安排。"""
    if type(capacity) is not int or not 1<=capacity<=100:
        raise ValueError("审理席位配额须在 1 至 100")
    cfg,cases,clocks,scored,docs,hearings,ledger=prepare_inputs(capacity)
    validate_absences(absences,cfg["reviewers"])
    result=reissue_shift(cases.active,clocks,scored,docs,cfg,capacity,hearings,absences,ledger)
    return build_reissue_packet(result,absences)


def validate_absences(absences, reviewers):
    handles={row["handle"] for row in reviewers}
    if not isinstance(absences,dict) or not absences:
        raise ValueError("缺班清单须为非空对象")
    for handle,span in absences.items():
        if handle not in handles:
            raise ValueError("缺班人员须在已发布班表内")
        if not isinstance(span,(list,tuple)) or len(span)!=2 or any(type(t) is not int for t in span):
            raise ValueError("缺班应有两个整数分钟端点")
        if span[0]<0 or span[0]>=span[1]:
            raise ValueError("缺班时间倒序或不合法")
