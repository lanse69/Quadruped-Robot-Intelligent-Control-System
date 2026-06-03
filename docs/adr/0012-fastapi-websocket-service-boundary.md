# ADR-0012: FastAPI / WebSocket 服务化边界

## 状态

Accepted

## 背景

当前仓库已经具备依赖标准库的 API Facade、本机 Minimal / MuJoCo 仿真 runner、控制状态、回放索引和审计事件基础能力。但接口仍停留在 Python 函数调用层，尚不能满足控制台通过 HTTPS / WebSocket 接入的设计边界。

需求和设计要求 Console -> API 采用 HTTPS / JSON，Telemetry -> Monitor 采用 Message Bus / WebSocket，且所有请求应携带 requestId 并进入统一接口入口。

## 决策

新增 `python/qrics/api/http_app.py` 作为 FastAPI 传输适配层：

- 以 `/api/v1` 暴露任务、控制、训练、策略、回放、审计和事件查询接口。
- 以 `/api/v1/ws/events` 暴露事件快照 WebSocket 接口。
- HTTP 层只做上下文解析、payload 转换、错误映射和事件输出。
- 业务规则继续由 `QricsApiApp` 和既有领域对象承载。
- `qrics.api.__init__` 不导入 FastAPI 模块，避免未安装 `api` extra 时破坏轻量测试。

## 后果

正面：

- 控制台或后续前端可以通过真实 HTTP / WebSocket 运行链路接入。
- API 测试能覆盖角色约束、错误映射、handoff 仿真上下文和回放时间戳一致性。
- 后续替换为持久化 repository 或消息总线时，可保持 HTTP schema 与 WebSocket 事件信封稳定。

代价：

- 新增可选依赖 `fastapi`、`uvicorn[standard]` 和开发依赖 `httpx`。
- 当前 WebSocket 先输出事件快照；实时增量订阅需要下一阶段消息总线或异步事件源。