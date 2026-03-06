# Mappers

负责将各数据源的原始 API 数据映射为标准 `JobCreate` 结构。

## 架构设计

### BaseMapper

所有 mapper 继承自 `BaseMapper`，提供：

- 抽象方法
  - `source_name`：数据源标识符
  - `map(raw_job)`：将原始 payload 映射为 `JobCreate`
- 工具方法
  - `_clean(value)`：清理字符串，去除空白
  - `_to_datetime_or_none(value)`：解析多种时间格式
  - `normalize_country_field(raw_value)`：标准化国家代码

## 当前字段映射契约

### 必填字段

| 字段 | 说明 |
|------|------|
| `source` | 兼容输入键（`platform:identifier` 风格）；持久化归属以 `source_id` 为准 |
| `external_job_id` | 外部系统职位 ID |
| `title` | 职位名称 |
| `apply_url` | 申请链接 |

### 关键可选字段

| 字段 | 说明 |
|------|------|
| `location_hints` | 位置提示列表。每项可包含 `source_raw/city/region/country_code/workplace_type/remote_scope` |
| `department` | 部门 |
| `team` | 团队 |
| `employment_type` | 雇佣类型 |
| `description_html` | HTML 格式职位描述（后续由 blob 管理器处理） |
| `description_plain` | 纯文本职位描述（可空，服务层可从 HTML 补齐） |
| `published_at` | 发布时间 |
| `source_updated_at` | 源系统更新时间 |
| `raw_payload` | 原始 API 响应（后续由 blob 管理器处理） |

说明：

- `location_text/location_city/location_region/location_country_code/location_workplace_type` 等旧字段已不再属于 `JobCreate` 契约。
- `description_html` 与 `raw_payload` 不是 `job` 表内联列，实际持久化走 blob pointer/hash 列。

## 错误处理规则

- 缺失字段返回 `None`
- 空字符串转为 `None`
- 无效日期转为 `None`

## 已支持的数据源

| Mapper | 数据源 |
|--------|--------|
| `GreenhouseMapper` | Greenhouse |
| `LeverMapper` | Lever |
| `AshbyMapper` | Ashby |
| `SmartRecruitersMapper` | SmartRecruiters |
| `EightfoldMapper` | Eightfold |
| `AppleMapper` | Apple |
| `UberMapper` | Uber |
| `TikTokMapper` | TikTok |

## 添加新的 Mapper

```python
from typing import Any

from app.ingest.mappers.base import BaseMapper
from app.schemas.job import JobCreate
from app.services.domain.location import extract_workplace_type, parse_location_text


class NewPlatformMapper(BaseMapper):
    @property
    def source_name(self) -> str:
        return "newplatform"

    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        location_text = self._clean(raw_job.get("location"))
        parsed = parse_location_text(location_text)
        workplace_type = extract_workplace_type([location_text])

        return JobCreate(
            source=self.source_name,
            external_job_id=str(raw_job.get("id", "")),
            title=self._clean(raw_job.get("title")),
            apply_url=self._clean(raw_job.get("url")),
            normalized_apply_url=None,
            status="open",
            location_hints=[
                {
                    "source_raw": location_text,
                    "city": parsed.city,
                    "region": parsed.region,
                    "country_code": parsed.country_code,
                    "workplace_type": workplace_type,
                    "remote_scope": parsed.remote_scope,
                }
            ]
            if (location_text or parsed.city or parsed.region or parsed.country_code)
            else [],
            department=self._clean(raw_job.get("department")),
            team=None,
            employment_type=None,
            description_html=self._clean(raw_job.get("description")),
            description_plain=None,
            published_at=self._to_datetime_or_none(raw_job.get("posted_at")),
            source_updated_at=self._to_datetime_or_none(raw_job.get("updated_at")),
            raw_payload=raw_job,
        )
```

## 时间解析支持

`_to_datetime_or_none()` 支持以下格式：

- ISO 8601 字符串：`"2024-01-15T10:30:00Z"`
- Unix 时间戳（秒）：`1705315800`
- Unix 时间戳（毫秒）：`1705315800000`
- 数字字符串：`"1705315800"`

## 测试

```bash
pytest tests/unit/ingest/mappers/
```
