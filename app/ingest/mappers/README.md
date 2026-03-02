# Mappers

负责将各数据源的原始 API 数据映射为标准 `JobCreate` 格式的模块。

## 架构设计

### BaseMapper

所有 mapper 继承自 `BaseMapper`，提供：

- **抽象方法**：
  - `source_name` - 数据源标识符
  - `map(raw_job)` - 将原始数据映射为 `JobCreate`

- **工具方法**：
  - `_clean(value)` - 清理字符串，去除空白
  - `_to_datetime_or_none(value)` - 解析多种时间格式
  - `normalize_country_field(raw_value)` - 标准化国家代码

### 字段映射规则

**必填字段**：
| 字段 | 说明 |
|------|------|
| `source` | 数据源标识符（固定值） |
| `external_job_id` | 外部系统的职位 ID |
| `title` | 职位名称 |
| `apply_url` | 申请链接 |

**可选字段**：
| 字段 | 说明 |
|------|------|
| `location_text` | 工作地点原始文本 |
| `location_city` | 解析后的城市 |
| `location_region` | 解析后的省/州 |
| `location_country_code` | 解析后的国家代码 (ISO 3166-1) |
| `location_workplace_type` | 工作模式 (remote/hybrid/onsite) |
| `department` | 部门 |
| `team` | 团队 |
| `employment_type` | 雇佣类型 (full-time/part-time/contract) |
| `description_html` | HTML 格式职位描述 |
| `description_plain` | 纯文本职位描述 |
| `published_at` | 发布时间 |
| `source_updated_at` | 数据源更新时间 |
| `raw_payload` | 原始 API 响应（完整保留） |

### 错误处理规则

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
from app.services.domain.job_location import extract_workplace_type, parse_location_text


class NewPlatformMapper(BaseMapper):
    """NewPlatform data mapper."""

    @property
    def source_name(self) -> str:
        return "newplatform"

    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        location_text = self._clean(raw_job.get("location"))
        parsed_loc = parse_location_text(location_text)

        return JobCreate(
            source=self.source_name,
            external_job_id=str(raw_job.get("id", "")),
            title=self._clean(raw_job.get("title")),
            apply_url=self._clean(raw_job.get("url")),
            normalized_apply_url=None,
            status="open",
            location_text=location_text,
            location_city=parsed_loc.city,
            location_region=parsed_loc.region,
            location_country_code=parsed_loc.country_code,
            location_workplace_type=extract_workplace_type([location_text]),
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

## 使用示例

```python
from app.ingest.mappers import GreenhouseMapper

mapper = GreenhouseMapper()
job_create = mapper.map(raw_job_data)
```

## 测试

```bash
pytest tests/unit/ingest/mappers/
```
