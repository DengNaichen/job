# Job Service

职位聚合微服务，用于从多个数据源抓取、去重和存储职位信息。

## 项目结构

```
app/
├── main.py              # FastAPI 入口
├── api/v1/              # API 路由
│   ├── router.py        # 路由聚合
│   └── jobs.py          # Job CRUD 端点
├── core/                # 核心配置
│   ├── config.py        # 环境变量
│   └── database.py      # 数据库连接
├── models/              # 数据模型
│   ├── job.py           # Job 模型
│   └── sync_run.py      # SyncRun 模型
├── schemas/             # Pydantic schemas
│   └── job.py           # 请求/响应模型
├── services/            # 业务逻辑
└── repositories/        # 数据库操作
```

## 数据模型

### Job

职位信息表，存储从外部源同步的职位数据。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| source | str | 数据源标识 (e.g. ashby, greenhouse) |
| external_job_id | str | 外部系统的职位 ID |
| title | str | 职位标题 |
| apply_url | str | 申请链接 |
| status | enum | 职位状态 (open/closed) |
| normalized_apply_url | str | 标准化 URL，用于跨源去重 |
| content_fingerprint | str | 内容哈希，检测内容变化 |
| dedupe_group_id | str | 去重组标识 |
| raw_payload | JSON | 原始数据，保留完整信息 |

### SyncRun

同步任务记录表，追踪每次同步的执行状态和统计。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| source | str | 数据源 |
| status | enum | 运行状态 (running/success/failed) |
| fetched_count | int | 获取数量 |
| inserted_count | int | 新增数量 |
| updated_count | int | 更新数量 |
| closed_count | int | 关闭数量 |
| failed_count | int | 失败数量 |

## 快速开始

```bash
# 安装依赖
./scripts/uv sync

# 配置环境变量
cp .env.example .env

# 启动服务
./scripts/uv run uvicorn app.main:app --reload

# 访问文档
open http://localhost:8000/docs
```

## 数据库迁移

数据库迁移目录是本地私有维护，不随这个仓库公开发布。
如果你在本地维护了 Alembic 子仓库，请在那里生成并执行迁移。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| GET | /api/v1/jobs | 获取职位列表 |
| GET | /api/v1/jobs/{id} | 获取单个职位 |
| POST | /api/v1/jobs | 创建职位 |
| PATCH | /api/v1/jobs/{id} | 更新职位 |
| DELETE | /api/v1/jobs/{id} | 删除职位 |
