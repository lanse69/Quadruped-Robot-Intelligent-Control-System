# ADR-0015：API 类型安全与 RBAC 策略单一事实源

## 状态

Accepted

## 背景

API Facade 与 HTTP 传输层已经承担任务、控制、训练、策略、回放、事件和审计入口。前序实现中，权限判断、高风险操作策略、HTTP 枚举值转换和动态 JSON 响应读取分散在多个文件中，容易造成以下问题：

- `app.py` 与 `security.py` 存在重复 RBAC 语义时，角色权限和高风险 reason 策略会漂移。
- HTTP header 中的角色、控制覆盖命令和门禁结论来自字符串边界，需要运行时校验后才能构造强类型 payload。
- `ApiResponse.data` 使用裸 `dict[str, object]` 时，严格 mypy 会把 `count`、`records` 等字段视为不可比较、不可迭代的 `object`。
- WebSocket 事件快照不能由传输层隐式提升为 `auditor`，否则会破坏统一权限语义。
- 当前项目环境保留 `httpx2` 作为 HTTP 测试链路 warning 抑制/兼容依赖，同时继续保留官方 `httpx` 依赖；该决策属于本机开发体验约束，不改变 API 业务语义。

## 决策

- `python/qrics/api/security.py` 是 API 权限矩阵、高风险操作策略、override action 映射、角色规范化和 gate decision 校验的唯一事实源。
- `QricsApiApp` 只调用 `authorize()`、`high_risk_operation()` 和 `action_for_override()`，不维护私有权限矩阵。
- HTTP 适配层在构造 `RequestContext`、`OverridePayload`、`GateReportPayload` 前完成运行时校验和类型收窄。
- 缺失或未知的 HTTP/WebSocket 角色统一规范化为非提权 `operator`；非法 override command 和非法 gate decision 仍返回 `422 INVALID_REQUEST`。
- `ApiResponse.data` 使用递归 JSON 类型表达；测试在读取动态 JSON 字段前通过 helper 做显式类型收窄。
- WebSocket `/api/v1/ws/events` 使用与 HTTP API 一致的上下文规则，不再硬编码 `auditor`。
- `httpx2` 暂时保留在 `dev` 与 `all` extras 中，并在文档中声明其用途。

## 影响

- API 权限策略不会在 Facade 与 HTTP 层之间漂移。
- 未知传输角色不会获得训练、策略发布、审计查询等高权限。
- 严格类型检查可以理解动态 JSON 响应字段的读取逻辑。
- 安全策略单元测试、HTTP 权限测试和 WebSocket 上下文测试可以分别覆盖策略、传输和事件边界。
- 开发依赖口径与用户当前环境诉求保持一致，但 `httpx2` 不被描述为生产运行依赖。