# Location 拆表执行计划

## 目标

- `job` 不再承载结构化 `location_*` 字段。
- 结构化位置统一存储在 `locations + job_locations`。
- 保持迁移过程可回滚、可分阶段发布。

## 当前进度（2026-03-02）

- 已完成：阶段 2、阶段 3、阶段 4、阶段 5、阶段 6、阶段 7（代码、迁移与本地验证已落地）。
- 待完成：阶段 9 的第二次发布窗口（生产发布与回滚预案演练）。
- 阶段 1 决策：`job.location_text` 已移除，展示原文统一使用 `job_locations.source_raw`。

## 阶段 1：范围冻结与决策

1. 明确是否保留 `job.location_text`。
2. 冻结 location 相关接口变更范围，避免迁移中途需求漂移。
3. 确认兼容窗口（是否需要老客户端继续读旧字段）。

## 阶段 2：新表能力补齐（不删旧列）

1. 在 `job_locations` 增加：
1. `workplace_type`
2. `remote_scope`
2. 为常用查询增加索引（例如 primary location 读取路径）。
3. 保持旧列仍存在，先不删除。

## 阶段 3：数据回填迁移（Alembic 第 1 波）

1. 将 `job.location_*` 历史数据回填到每个 job 的 primary `job_location`。
2. 对缺失 primary link 的 job 创建 primary link。
3. 回填逻辑必须幂等（可重复执行不出错）。

## 阶段 4：写路径切换

1. 导入/同步链路只写 `locations/job_locations`。
2. 禁止新代码写 `job.location_*`。
3. 保留旧列仅用于过渡期读取。

## 阶段 5：读路径切换

1. 匹配查询只从 `job_locations + locations` 读取结构化位置。
2. 去掉对 `job.location_*` 的 fallback。
3. API 返回的 `locations` 作为主结构化位置来源。

## 阶段 6：Schema / API 清理

1. `JobCreate/JobUpdate/JobRead` 去除或标记废弃：
1. `location_city`
2. `location_region`
3. `location_country_code`
4. `location_workplace_type`
5. `location_remote_scope`
2. 如需兼容老客户端，设置一个明确的字段废弃窗口。

## 阶段 7：删除旧列（Alembic 第 2 波）

1. 删除 `job` 的结构化 location 兼容列：
1. `location_city`
2. `location_region`
3. `location_country_code`
4. `location_workplace_type`
5. `location_remote_scope`
2. 删除 `location_text`，并在删列前将缺失 primary link 的少量存量数据补齐到 `job_locations.source_raw`。
3. 同步清理相关旧索引与死代码。

## 阶段 8：测试与验证

1. 单测：
1. `full_snapshot_sync`
2. `match_query`
3. `match_service`
4. job API 相关
2. 集成验证：
1. 运行 `greenhouse:airbnb` 冷启动导入
2. 运行 `greenhouse:airbnb` 热启动导入
3. 迁移验证：
1. 使用旧库快照升级
2. 验证无数据丢失
3. 验证读写行为一致

## 阶段 9：发布策略

1. 两次发布：
1. 第一次：加列 + 回填 + 双读兼容
2. 第二次：去 fallback + 删旧列
2. 每次发布都准备可回滚方案。

## 完成标准（DoD）

1. 业务路径中不再读写 `job.location_*`（迁移脚本除外）。
2. 导入与同步仅写 `locations/job_locations`。
3. 匹配和 API 全量测试通过。
4. 冷/热启动性能无明显退化。
