# QRICS API 草案 v0.1

本文件记录应用接口、状态推送和答辩演示所需的 API 族。当前阶段不启动 HTTP 服务；`python/qrics/api` 中的 route facade 函数作为后续 FastAPI / WebSocket 适配的稳定边界。

## 1. 通用约定

- 所有请求都携带 `request_id`、`actor_id`、`role`。
- 所有响应统一使用 `ApiResponse`：`ok`、`data`、`errors`、`request_id`。
- 当前阶段只使用内存状态，不接数据库、对象存储、消息总线或真实 Isaac Lab。
- 高风险操作必须写入审计：急停、任务取消、策略发布、策略基线切换。

## 2. Task API

| 接口 | facade 函数 | 输入 | 输出 |
|---|---|---|---|
| `POST /api/v1/tasks` | `routes_tasks.submit_task` | `TaskSubmissionPayload` | `TaskPreviewResponse` |
| `POST /api/v1/tasks/{task_id}/confirm` | `routes_tasks.confirm_task` | `task_id` | `TaskLifecycleResponse` |
| `POST /api/v1/tasks/{task_id}/handoff` | `routes_tasks.handoff_task` | `task_id` | `ControlStatusResponse` |
| `POST /api/v1/tasks/{task_id}/cancel` | `routes_tasks.cancel_task` | `task_id`, `reason` | `TaskLifecycleResponse` |

## 3. Control API

| 接口 | facade 函数 | 输入 | 输出 |
|---|---|---|---|
| `GET /api/v1/control/runs/{run_id}` | `routes_control.get_control_status` | `run_id` | `ControlStatusResponse` |
| `POST /api/v1/control/runs/{run_id}/override` | `routes_control.override_control` | `OverridePayload` | `ControlStatusResponse` |

当前 `OverridePayload.command_type` 支持：`emergency_stop`、`manual_control`、`safe_stand`、`pause`、`resume`。

## 4. Training API

| 接口 | facade 函数 | 输入 | 输出 |
|---|---|---|---|
| `POST /api/v1/training/jobs` | `routes_training.submit_training_plan` | `TrainingPlanPayload` | `TrainingJobResponse` |

## 5. Policy API

| 接口 | facade 函数 | 输入 | 输出 |
|---|---|---|---|
| `POST /api/v1/policies` | `routes_policies.register_policy` | `PolicyRegistrationPayload` | `PolicyStateResponse` |
| `POST /api/v1/policies/{policy_ref}/gate` | `routes_policies.attach_gate_report` | `GateReportPayload` | `PolicyStateResponse` |
| `POST /api/v1/policies/{policy_ref}/release` | `routes_policies.release_policy` | `ResourceRef`, `reason` | `PolicyStateResponse` |
| `POST /api/v1/policies/{policy_ref}/baseline` | `routes_policies.promote_policy_baseline` | `ResourceRef`, `reason` | `PolicyStateResponse` |

发布和基线切换要求 `role` 为 `algorithm_engineer` 或 `admin`。未通过 gate 的策略不得 release。

## 6. Replay / Audit API

| 接口 | facade 函数 | 输入 | 输出 |
|---|---|---|---|
| `GET /api/v1/replay/runs/{run_id}` | `routes_replay.query_replay` | `ReplayQuery` | `ReplayResponse` |
| `GET /api/v1/audit` | `routes_audit.query_audit` | `AuditQuery` | `count`, `audit_ids` |

## 7. 后续 HTTP 化映射原则

后续引入 FastAPI 时，不改 `schemas.py` 和 route facade 的业务语义，只新增薄适配层：HTTP 请求体转换为 dataclass，调用 facade 函数，再把 `ApiResponse` 转为 JSON 响应。