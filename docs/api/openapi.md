# QRICS API Facade 契约 v0.2

本文档描述 QRICS 应用接口族、请求/响应结构、状态推送和后续 HTTP 化映射原则。当前仓库不启动 HTTP 服务；`python/qrics/api` 中的 route facade 函数是后续 FastAPI / WebSocket 适配层的稳定业务边界。

## 1. 设计边界

当前 API Facade 的目标是让任务执行、控制状态、训练作业、策略治理、回放索引和审计记录在无数据库、无消息总线、无 FastAPI 的条件下可测试、可演示。

约束：

- API 层不得接收或下发未经过安全语义建模的底层关节命令。
- API 层不暴露 MuJoCo、Isaac Lab、Webots 等后端内部对象。
- 进入仿真后端的动作必须是 `SafeAction`；被拒绝的 `SafeAction` 必须在后端命令映射阶段再次阻断。
- 高风险操作必须记录审计：急停、任务取消、策略发布、策略基线切换。
- 当前所有状态保存在内存中，重启后丢失；持久化属于后续服务化阶段。

## 2. 通用请求上下文

所有 Facade 调用显式携带 `RequestContext`。

| 字段 | 类型 | 说明 |
|---|---:|---|
| `request_id` | string | 请求 ID，用于串联 API 响应、事件和审计。 |
| `actor_id` | string | 操作者 ID。 |
| `role` | string | `operator`、`algorithm_engineer`、`test_engineer`、`admin`、`auditor`。 |

后续 HTTP 化时，`request_id` 可来自请求头 `X-Request-Id`；`actor_id` 与 `role` 应来自认证上下文，不应信任客户端任意传入。

## 3. 通用响应结构

所有 route facade 返回 `ApiResponse`。

| 字段 | 类型 | 说明 |
|---|---:|---|
| `ok` | boolean | 调用是否成功。 |
| `data` | object | 成功响应内容；失败时为空对象。 |
| `errors` | array | 失败响应错误列表。 |
| `request_id` | string | 原请求 ID。 |

错误对象：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `code` | string | 错误码，例如 `NOT_FOUND`、`CONFLICT`、`FORBIDDEN`、`INVALID_REQUEST`。 |
| `message` | string | 错误说明。 |
| `field` | string | 可选；参数错误对应字段。 |

## 4. Task API

| HTTP 草案 | Facade 函数 | 输入 | 输出 |
|---|---|---|---|
| `POST /api/v1/tasks` | `routes_tasks.submit_task` | `TaskSubmissionPayload` | `TaskPreviewResponse` |
| `POST /api/v1/tasks/{task_id}/confirm` | `routes_tasks.confirm_task` | `task_id` | `TaskLifecycleResponse` |
| `POST /api/v1/tasks/{task_id}/handoff` | `routes_tasks.handoff_task` | `task_id` | `ControlStatusResponse` |
| `POST /api/v1/tasks/{task_id}/cancel` | `routes_tasks.cancel_task` | `task_id`, `reason` | `TaskLifecycleResponse` |

### 4.1 `TaskSubmissionPayload`

| 字段 | 类型 | 默认值 | 说明 |
|---|---:|---|---|
| `source_text` | string | 无 | 中文自然语言任务文本。 |
| `scene_ref` | `ResourceRef` | `minimal_scene:0.1.0` | 场景引用。 |
| `require_confirmation` | boolean | `true` | 是否要求操作者确认后 handoff。 |

当前规则解析支持 `A`、`B`、`平台` 三类演示路径点。无法匹配路径点时，任务进入 `rejected`。

### 4.2 `TaskPreviewResponse`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `task_id` | string | 任务 ID。 |
| `state` | string | `preview_ready` 或 `rejected`。 |
| `goal` | string | 原始任务文本。 |
| `waypoints` | array[string] | 解析出的路径点 ID。 |
| `selected_policy_reason` | string | 策略选择解释。 |
| `risk_summary` | string | 执行前风险说明。 |
| `operator_action_required` | boolean | 是否需要操作者确认。 |

### 4.3 任务状态流转

```text
submit_task -> preview_ready -> confirm_task -> confirmed -> handoff_task -> handed_off
submit_task -> rejected
preview_ready / confirmed -> cancel_task -> cancelled
```

`handoff_task` 只接受 `confirmed` 状态任务。`cancel_task` 不允许取消已经 `handed_off` 或 `cancelled` 的任务。

## 5. Control API

| HTTP 草案 | Facade 函数 | 输入 | 输出 |
|---|---|---|---|
| `GET /api/v1/control/runs/{run_id}` | `routes_control.get_control_status` | `run_id` | `ControlStatusResponse` |
| `POST /api/v1/control/runs/{run_id}/override` | `routes_control.override_control` | `OverridePayload` | `ControlStatusResponse` |

### 5.1 `ControlStatusResponse`

`ControlStatusResponse` 表示任务 handoff 后的控制运行状态。当前本机演示接入后应包含仿真上下文字段。

| 字段 | 类型 | 说明 |
|---|---:|---|
| `run_id` | string | 控制运行 ID，例如 `run_task_1`。 |
| `state` | string | `created`、`running`、`paused`、`succeeded`、`failed`、`cancelled`。 |
| `current_node_id` | string | 当前任务图节点。 |
| `completed_node_count` | number | 已完成节点数量。 |
| `control_step_count` | number | 已执行控制步数。 |
| `risk_score` | number | 当前风险分数。 |
| `latest_action` | string | 最新安全动作，例如 `body_velocity`、`stop`、`safe_stand`。 |
| `reason` | string | 状态原因。 |
| `backend` | string | `minimal`、`mujoco`、后续 `isaac_lab` 或 `webots`。 |
| `runtime_profile` | string | `headless_fast`、`balanced_visual`、`rich_demo`。 |
| `sim_time_ns` | number | 仿真时间戳。 |
| `base_position` | array[number] | 机器人 base 位置 `[x, y, z]`。 |
| `observation_quality` | string | `direct`、`estimated`、`missing` 等观测来源质量。 |

示例：

```json
{
  "run_id": "run_task_1",
  "state": "running",
  "current_node_id": "move_0",
  "completed_node_count": 0,
  "control_step_count": 20,
  "risk_score": 0.0,
  "latest_action": "body_velocity",
  "reason": "Task handed off to minimal simulation runner",
  "backend": "minimal",
  "runtime_profile": "headless_fast",
  "sim_time_ns": 800000000,
  "base_position": [0.05, 0.0, 0.32],
  "observation_quality": "estimated"
}
```

### 5.2 `OverridePayload`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `command_type` | string | `emergency_stop`、`manual_control`、`safe_stand`、`pause`、`resume`。 |
| `reason` | string | 操作者或系统原因。 |

行为约束：

- `emergency_stop` 将运行置为 `paused`，最新动作为 `stop`，并追加 `control.emergency_stop` 审计记录。
- `safe_stand` 将运行置为 `paused`，最新动作为 `safe_stand`。
- `resume` 将运行置为 `running`。
- `manual_control` 与 `pause` 当前按暂停/停止语义处理，后续可扩展为人工接管状态机。

## 6. Training API

| HTTP 草案 | Facade 函数 | 输入 | 输出 |
|---|---|---|---|
| `POST /api/v1/training/jobs` | `routes_training.submit_training_plan` | `TrainingPlanPayload` | `TrainingJobResponse` |

### 6.1 `TrainingPlanPayload`

| 字段 | 类型 | 默认值 | 说明 |
|---|---:|---|---|
| `training_id` | string | 无 | 训练计划 ID。 |
| `scene_ref` | `ResourceRef` | 无 | 场景引用。 |
| `algorithm` | string | `ppo_placeholder` | 算法名称。 |
| `max_iterations` | number | `100` | 最大迭代数，必须大于 0。 |
| `num_envs` | number | `1` | 并行环境数量，必须大于 0。 |
| `seed` | number | `42` | 随机种子。 |

当前 Facade 只创建 `queued` 作业，不执行真实强化学习训练。

## 7. Policy API

| HTTP 草案 | Facade 函数 | 输入 | 输出 |
|---|---|---|---|
| `POST /api/v1/policies` | `routes_policies.register_policy` | `PolicyRegistrationPayload` | `PolicyStateResponse` |
| `POST /api/v1/policies/{policy_ref}/gate` | `routes_policies.attach_gate_report` | `GateReportPayload` | `PolicyStateResponse` |
| `POST /api/v1/policies/{policy_ref}/release` | `routes_policies.release_policy` | `ResourceRef`, `reason` | `PolicyStateResponse` |
| `POST /api/v1/policies/{policy_ref}/baseline` | `routes_policies.promote_policy_baseline` | `ResourceRef`, `reason` | `PolicyStateResponse` |

发布和基线切换要求：

- `role` 必须是 `algorithm_engineer` 或 `admin`。
- 策略必须先通过 gate，才能 release。
- 只有 `released` 或已有 `baseline` 状态策略可以被提升为当前 baseline。
- 发布和基线切换必须写入审计。

策略状态机：

```text
candidate -> gate_passed -> released -> baseline
candidate -> gate_failed
baseline -> released   # 当新 baseline 被提升时，旧 baseline 回退为 released
```

## 8. Replay API

| HTTP 草案 | Facade 函数 | 输入 | 输出 |
|---|---|---|---|
| `GET /api/v1/replay/runs/{run_id}` | `routes_replay.query_replay` | `ReplayQuery` | `ReplayResponse` |

`ReplayResponse` 当前用于保存 API handoff 演示回放索引。

| 字段 | 类型 | 说明 |
|---|---:|---|
| `run_id` | string | 控制运行 ID。 |
| `segment_count` | number | 回放片段数量。 |
| `keyframe_count` | number | 关键帧数量。 |
| `backend` | string | 回放对应仿真后端。 |
| `runtime_profile` | string | 回放对应运行档位。 |
| `first_timestamp_ns` | number | 回放时间窗起点。 |
| `last_timestamp_ns` | number | 回放时间窗终点。 |
| `keyframes` | array[string] | 关键帧 ID 列表。 |

## 9. Audit API

| HTTP 草案 | Facade 函数 | 输入 | 输出 |
|---|---|---|---|
| `GET /api/v1/audit` | `routes_audit.query_audit` | `AuditQuery` | `count`, `audit_ids` |

`AuditQuery` 支持按 `actor_id`、`object_id`、`action` 过滤。当前返回审计 ID 列表；后续服务化阶段应增加分页、时间范围、角色过滤和完整记录读取接口。

## 10. Event API / WebSocket 映射

当前代码通过 `app.event_stream.list_events()` 和 `app.event_stream.query(...)` 读取内存事件。后续 HTTP/WebSocket 映射建议：

| HTTP / WS 草案 | 当前 Facade | 说明 |
|---|---|---|
| `GET /api/v1/events?run_id=...&topic=...` | `InMemoryEventStream.query` | 调试和测试用事件查询。 |
| `WS /api/v1/events/stream` | 后续薄适配层 | 推送 `EventEnvelope`，不得改变信封结构。 |

事件主题详见 [`docs/api/events.md`](events.md)。

## 11. 仿真后端选择

API Facade 不暴露仿真平台私有对象，只暴露后端选择和运行档位。

建议后续 HTTP 请求字段：

```json
{
  "backend": "mujoco",
  "runtime_profile": "balanced_visual"
}
```

允许值：

| 字段 | 允许值 | 说明 |
|---|---|---|
| `backend` | `minimal`, `mujoco`, `webots`, `isaac_lab` | `minimal` 用于无外部依赖测试；`mujoco` 用于本机真实物理演示；`isaac_lab` 仍是需求/设计基线。 |
| `runtime_profile` | `headless_fast`, `balanced_visual`, `rich_demo` | `headless_fast` 用于 CI 和 smoke；`balanced_visual` 用于本机窗口演示；`rich_demo` 预留录制和富传感器演示。 |

当前 API Facade 默认值：

```text
backend = minimal
runtime_profile = headless_fast
```

## 12. HTTP 化原则

后续引入 FastAPI 时：

1. 不修改 `schemas.py` 的业务字段语义。
2. 不把 HTTP handler 写成业务逻辑承载层；handler 只做认证、请求体转换、调用 facade、响应序列化。
3. `ApiResponse.ok=false` 映射到合适 HTTP 状态码，但错误码仍保留在响应体中。
4. 高风险操作的 `reason` 字段必须保留，不能由 HTTP 层丢弃。
5. WebSocket 推送使用 `EventEnvelope`，不得以临时前端字段替代正式事件信封。