# 占道工单逾期审理 · 验证索引

AI/ML / 传统ML · 市政占道工单逾期预测与许可复核排班

阶段证据包含开办、停办和补正分钟的守恒台账，按结案时点向前滚动的校准回放，以及同等席位下模型顺序与剩余法定时间顺序的复核差异。缺班演练保留调整前后的人员、签审时段及辖区时限变化。结案流水可对照正式排班逐单审阅。

## 功能模块

| 模块 | 业务职责 | 计算规则 | 核心位置 | 独立测试 |
|---|---|---|---|---|
| M1 | 许可流转 | 标准道路名去重、锁定可见修订与材料清单，隔离撤回和同版冲突 | `src/permitdesk/permit_intake/inbox.py` `src/permitdesk/permit_intake/contracts.py` `src/permitdesk/permit_intake/service.py` | `tests/test_permit_intake.py` |
| M2 | 日历折算 | 按半开班表剔除节假日及材料补正暂停，换算实际审理分钟和截止时刻 | `src/permitdesk/calendar_intervals/business_time.py` `src/permitdesk/calendar_intervals/contracts.py` `src/permitdesk/calendar_intervals/service.py` | `tests/test_calendar_intervals.py` |
| M3 | 审理特征 | 占道范围、法定消耗、材料和辖区负载形成时点特征并隔离迟结案标签 | `src/permitdesk/review_features/snapshot.py` `src/permitdesk/review_features/contracts.py` `src/permitdesk/review_features/service.py` | `tests/test_review_features.py` |
| M4 | 超期概率 | 逻辑回归处理少数超期，冻结缩放，用独立留出桶保序校准并检查异常工况 | `src/permitdesk/deadline_classifier/classifier.py` `src/permitdesk/deadline_classifier/contracts.py` `src/permitdesk/deadline_classifier/service.py` | `tests/test_deadline_classifier.py` |
| M5 | 审理编组 | 按应急和法定剩余时间排队，强制辖区、资质、班内时段及大占道双签审 | `src/permitdesk/review_roster/staffing.py` `src/permitdesk/review_roster/contracts.py` `src/permitdesk/review_roster/service.py` | `tests/test_review_roster.py` |
| M6 | 许可追溯 | 工单回执事后计算分组 AP、Brier 和空桶，验证双签证据和依赖版本摘要 | `src/permitdesk/permit_journal/ledger.py` `src/permitdesk/permit_journal/contracts.py` `src/permitdesk/permit_journal/service.py` | `tests/test_permit_journal.py` |

## 边界案例

| 陷阱 | 触发 | 错误做法 | 实现 | 位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-19 | 多个审理优先项冲突 | 按录入顺序 | 应急、时效、概率及许可编号优先级 | `src/permitdesk/review_roster/staffing.py` | `tests/test_review_roster.py::test_emergency_conflict_policy` |
| TRAP-22 | 道路别名台账顺序变化 | 按遍历第一条先到先得 | 标准映射和冲突检查 | `src/permitdesk/permit_intake/inbox.py` | `tests/test_permit_intake.py::test_road_alias_permutation` |
| TRAP-23 | 工作时钟与暂停相邻端点 | 双端计入 | 半开区间 | `src/permitdesk/calendar_intervals/business_time.py` | `tests/test_calendar_intervals.py::test_half_open_boundaries` |
| TRAP-25 | 日历版本同效冲突 | 顺序覆盖 | 隔离审批日历冲突 | `src/permitdesk/calendar_intervals/business_time.py` | `tests/test_calendar_intervals.py::test_version_conflict_and_effective_closure` |
| TRAP-31 | 极端 logit | 直接用不稳定指数 | 分支实现 | `src/permitdesk/deadline_classifier/classifier.py` | `tests/test_deadline_classifier.py::test_stable_rare_case_logit` |
| TRAP-32 | 常数列缩放 | 零标准差直接相除 | 尺度地板 | `src/permitdesk/deadline_classifier/classifier.py` | `tests/test_deadline_classifier.py::test_fixed_constant_scales` |
| TRAP-42 | 标签晚于拟合截面可见 | 先取最终工单状态 | 按结案时钟切分 | `src/permitdesk/review_features/snapshot.py` | `tests/test_review_features.py::test_closed_label_never_used_early` |
| TRAP-43 | 没有真实逾期 | 报告虚假的检索效果 | 平均精度明确未定义 | `src/permitdesk/permit_journal/ledger.py` | `tests/test_permit_journal.py::test_zero_positives_no_average_precision` |
| TRAP-44 | 未校准置信度排先后 | 把分类分数当真实概率 | 区间保序校准和分布外拦截 | `src/permitdesk/deadline_classifier/classifier.py` | `tests/test_deadline_classifier.py::test_isotonic_calibration_pooling` |
| TRAP-53 | 混长短工单改变概率 | 依赖当前推断批统计 | 冻结训练归一化 | `src/permitdesk/deadline_classifier/classifier.py` | `tests/test_deadline_classifier.py::test_inference_is_independent_of_batch` |
| TRAP-54 | 模型或日历变化 | 沿用老签审凭证 | 依赖签名重新生成 | `src/permitdesk/permit_journal/ledger.py` | `tests/test_permit_journal.py::test_source_model_and_calendar_invalidate_receipt` |
