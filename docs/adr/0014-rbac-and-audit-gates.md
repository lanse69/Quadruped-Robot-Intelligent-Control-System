# ADR-0014：RBAC 与高风险操作审计门控

## 状态

Accepted

## 背景

当前 API Facade 已经具备任务、控制、训练、策略、回放、审计和事件接口，但权限判断原先分散且不足。模型发布和基线切换有局部角色判断，训练提交、策略注册、门禁报告、审计查询和事件查询缺少统一 RBAC。HTTP 层部分接口如果没有 header，会默认获得 `algorithm_engineer` 或 `auditor` 权限，这不符合默认拒绝原则。

需求规格说明书要求系统采用 RBAC 区分任务执行、训练发布、系统管理等权限，并要求模型发布、回滚、删除等高风险动作写入审计日志并绑定操作者身份。软件设计说明书进一步要求高风险动作按角色、对象、状态和审批上下文联合判定，采用默认拒绝、审计先行和追加式审计链。

## 决策

1. 在 `QricsApiApp` 中建立应用层权限矩阵和高风险操作策略，作为当前代码阶段的权限语义单一事实源。
2. 任务、控制、训练、策略、回放、审计和事件入口统一执行权限检查。
3. 权限失败返回 `FORBIDDEN`，并追加审计记录，`result=denied`。
4. 高风险操作集中定义所需权限和是否强制 `reason`。
5. `control.emergency_stop` 不强制原因，避免急停路径被表单字段阻塞，但仍写入审计。
6. `policy.gate_report`、`policy.release`、`policy.promote_baseline` 等模型治理动作必须提供非空 `reason`。
7. 策略注册、门禁报告、发布、基线切换均写入审计记录。
8. 门禁未通过发布策略、非 released 策略提升 baseline 等业务拒绝路径写入审计记录，`result=rejected`。
9. HTTP 层不再为训练、策略、审计接口提供高权限默认角色；未显式声明角色时按 `operator` 处理。
10. `GET /api/v1/events` 使用统一 `ApiResponse` 封装，避免绕过权限错误模型。

## 后果

- API 权限行为更接近 V1.0 设计要求。
- 权限失败、缺少原因、门禁不满足等拒绝路径可追溯。
- 审计查询测试需要使用 `auditor` 或 `admin` 上下文。
- `operator` 仍可执行任务、急停、Safe-Stand、人工接管、回放和事件读取，但不能提交训练、注册策略、附加门禁报告、发布策略、切换基线或查询审计日志。
- 当前仍不是生产级认证系统；真实 token、会话、密钥保护、审批流和对象级授权后续继续实现。

## 验证

验证项包括：

- `operator` 提交训练计划返回 `403 FORBIDDEN`，并写入 `training.submit` / `denied` 审计。
- `algorithm_engineer` 可以提交训练、注册策略、附加门禁报告、发布策略和切换基线。
- 策略发布缺少 `reason` 返回 `422 INVALID_REQUEST`，并写入 `policy.release` / `rejected` 审计。
- `operator` 查询审计日志返回 `403 FORBIDDEN`，`auditor` 和 `admin` 可以查询。
- `STATE_CONFLICT` 在 HTTP 层映射为 409。
- WebSocket 快照完成事件携带 `timestamp_ns`。