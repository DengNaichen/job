# Skills 映射需求（对齐 spec002 US2）

本文是需求说明，不包含实现细节（目录结构、代码接口、脚本步骤、存储设计）。

## 对齐关系

- 对应 `specs/002-jd-structured-extraction/spec.md` 的 **User Story 2**。
- 关注点限定为：对已有 LLM 输出中的 `required_skills` 做规范化映射，以提升可检索与可比较性。

## User Story

作为 matching pipeline owner，我需要将 `required_skills` 规范化到稳定的 canonical 表达，以便后续过滤、统计、召回和排序使用一致语义。

## 需求边界

- 输入：已产出的 `required_skills` 列表。
- 输出：每个 skill 的规范化结果（可映射或未映射）。
- 范围：仅 `required_skills`。
- 不在本需求内：LLM 提取策略本身、prompt 设计、domain 规范化、数据库物理模型改造。

## 验收场景

1. **Given** `required_skills` 含常见别名或同义写法，**When** 进行规范化，**Then** 输出稳定 canonical 技能标签。
2. **Given** 输入 skill 无法可靠映射，**When** 进行规范化，**Then** 明确标记为未映射，不生成臆测标签。
3. **Given** 相同输入重复处理，**When** 多次运行，**Then** 输出结果保持一致（确定性）。
4. **Given** 批量 JD 输入，**When** 执行映射流程，**Then** 每条输入都返回对应结果且无静默丢失。

## 成功标准

- 规范化后技能可用于下游统一检索与比较。
- 映射覆盖率在迭代中可被持续度量并稳定提升。
- 失败或未映射案例可被追踪与复盘。
