# ADR-0013: Repository 与运行证据持久化边界

## 状态

Accepted

## 背景

系统已经具备 API Facade、FastAPI HTTP / WebSocket 传输入口、本机 Minimal / MuJoCo 仿真 runner、回放索引和审计事件基础能力。但 API Facade 仍使用进程内 dict/list 管理任务、控制、训练、策略、回放、审计和事件。服务重启后运行证据丢失，不满足实验元数据、模型版本、审计事件长期留存和历史回放引用完整性的要求。

## 决策

新增 Repository 持久化边界：

- `QricsRepository` 作为 API 应用层唯一状态接口。
- `InMemoryRepository` 用于轻量测试和单进程演示。
- `SQLiteQricsRepository` 用于本机开发和答辩演示的持久化元数据、审计索引和事件索引。
- `FileObjectStore` 用于写入不可变 replay/report/audit JSON 工件，并返回 `uri`、`checksum` 和 `size_bytes`。
- `ReplayResponse` 增加 `manifest_uri` 和 `manifest_checksum`。
- `AuditRecordResponse` 增加 `actor_role`、`request_id` 和 `timestamp_ns`。
- `EventEnvelope` 增加 `timestamp_ns`。

## 后果

正面：

- 服务重启后可查询历史 replay、audit 和 event。
- 回放清单具有不可变对象引用和 checksum。
- 后续替换为 PostgreSQL、对象存储或消息总线时，可保持 API Facade 业务方法稳定。
- 审计记录具备操作者、角色、请求编号和时间戳。

代价：

- 新增 SQLite schema 与序列化 / 反序列化代码。
- 本机运行会生成 `runtime/qrics-api/qrics.sqlite3` 与 `runtime/qrics-api/object_store/`，这些运行态文件不得提交。
- 当前实现仍不是生产级高可用数据库、对象存储或可靠消息总线。