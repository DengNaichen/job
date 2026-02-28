# MVP 可行性验证（按你当前方向）

## 结论（先说结果）
这条路线**可行**，但建议分两阶段：
1. **阶段 A（MVP）**：先完成“定时抓取 + 结构化入库 + Resume Matcher 打分 + 基础筛选 API”。
2. **阶段 B（再评估）**：在阶段 A 的查询性能/体验不足时，再接入 Algolia。

即：你现在的想法可以做，且**默认先不接 Algolia**更稳。

## 为什么先不接 Algolia
- 你现在核心价值是“匹配质量”（Resume Matcher）而不是“搜索体验极致化”。
- 现有栈（PostgreSQL）已能支持 MVP 的过滤、排序、分页，先验证用户是否真的需要毫秒级全文搜索。
- 提前接入 Algolia 会增加同步链路（DB -> Algolia）、运维面和排障复杂度。

## 目标验证问题（2 周内回答）
- Q1：是否能稳定拿到 Jobright/Simplify 的岗位数据并持续增量更新？
- Q2：Resume Matcher 的打分结果能否对岗位排序产生可感知价值？
- Q3：仅用 Postgres 查询，能否满足 MVP 的响应时间目标（例如 P95 < 500ms）？

## 最小技术方案（PoC）
- Ingest
  - 定时任务（cron/pgBoss）触发 `jobright`、`simplify` 抓取。
  - 标准化字段：`source`、`external_id`、`title`、`company`、`location`、`url`、`description`、`posted_at`。
  - 去重策略：`(source, external_id)` + `url` 兜底。
- Match
  - 使用 Resume Matcher 计算 `match_score`（0-100）。
  - 将 `match_score` 落库（支持按候选人维度重算）。
- API
  - `GET /jobs?source=&location=&min_score=&page=`
  - 默认排序：`match_score DESC, posted_at DESC`。
- Observability
  - 每次同步记录 `SyncRun`：拉取数、入库数、去重数、失败数、耗时。

## 验收标准（通过/不通过）
- 数据侧
  - 连续 7 天定时任务成功率 >= 95%。
  - 日增量岗位中重复率（同 source）<= 5%。
- 业务侧
  - 给定同一份简历，Top 20 结果人工抽样“相关岗位”占比 >= 60%。
- 性能侧
  - 列表查询 P95 < 500ms（无 Algolia）。

## 关键风险与控制
- 合规风险（最高优先）
  - Simplify Terms 明确限制未经授权的抓取/自动化访问，先确认授权边界再上生产抓取。
  - Jobright 需同样完成 ToS/robots 合规检查后再放量。
- 工程风险
  - 页面结构变更导致抓取失效：加字段级容错和失败告警。
  - 打分成本过高：先离线批处理 + 缓存分数，避免请求时同步计算。

## 里程碑（建议）
- Day 1-3：接通两个 source 的最小抓取 + 入库 + 去重。
- Day 4-6：接 Resume Matcher，完成分数落库与重算脚本。
- Day 7-9：API + 基础筛选排序 + 指标埋点。
- Day 10-14：稳定性观察与人工评估，输出“是否需要 Algolia”的决策。

## Algolia 决策门槛（再接入条件）
满足任一条再接入：
- 查询 P95 持续 > 500ms 且索引优化后仍不达标。
- 用户明确反馈“搜索体验”比“匹配准确性”更影响留存。
- 需要复杂全文检索（同义词、拼写纠错、高级 ranking）超出 DB 方案可接受成本。

## 参考
- Resume Matcher 仓库：<https://github.com/srbhr/Resume-Matcher>
- Simplify Terms（含自动化/抓取限制条款）：<https://simplify.jobs/terms>
