# ADR-0010: 应用接口、状态推送与演示 API Facade

## 状态

Accepted

## 背景

当前代码包已经具备领域模型、任务理解、任务编排、配置加载、任务执行器、监控回放审计模型、Python Isaac Lab Adapter 契约以及训练评测与模型治理基础。下一步需要给任务操作者、算法工程师、仿真测试工程师和系统管理员提供统一访问入口。

直接引入 FastAPI、WebSocket 服务、数据库和消息总线会放大运行依赖，并干扰当前以本机稳定演示为目标的开发节奏。因此本阶段先建立依赖标准库的 API Facade：固定请求/响应 schema、route facade 函数、事件主题和内存状态流。

## 决策

新增 `python/qrics/api`：

- `schemas.py` 定义 API 边界 dataclass。
- `errors.py` 统一错误响应。
- `event_stream.py` 提供内存事件流。
- `app.py` 提供 `QricsApiApp` 内存应用服务。
- `routes_*.py` 按 Task / Control / Training / Policy / Replay / Audit 划分 facade 函数。

新增 `tests/python/test_api_facade.py` 覆盖：

- 任务提交、确认、交接、控制状态查询。
- 急停覆盖控制运行并写入审计。
- 训练计划提交、策略注册、门禁通过、发布、基线切换。

## 不做内容

- 不启动 HTTP 服务。
- 不引入 FastAPI / Uvicorn / WebSocket 依赖。
- 不接数据库、对象存储或消息总线。
- 不接真实 Isaac Lab 仿真。
- 不替代 C++ 领域层和 Safety Shield；Python API Facade 只作为应用入口和演示边界。

## 后果

本阶段完成后，仓库可以在无 Isaac Lab 和无服务端框架的环境中演示端到端业务入口：任务提交、控制状态、急停审计、训练作业、策略发布、回放查询和事件流。后续引入 FastAPI / WebSocket 时，只需添加薄 HTTP 适配层，不需要重写领域语义。