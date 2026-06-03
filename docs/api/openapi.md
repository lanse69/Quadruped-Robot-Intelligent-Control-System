# QRICS HTTP API / API Facade 契约

本文档描述 QRICS 应用接口族、请求/响应结构、HTTP 映射、事件查询和 WebSocket 快照接口。当前仓库已经提供两层 API：

1. `python/qrics/api/app.py`：依赖标准库的 `QricsApiApp` 应用 Facade，承载任务、控制、训练、策略、回放、审计和事件流的业务边界。
2. `python/qrics/api/http_app.py`：可选 FastAPI / WebSocket 传输适配层，暴露 `/api/v1` HTTP 接口和 `/api/v1/ws/events` WebSocket 事件快照。

HTTP 层不得承载领域规则；它只负责请求上下文提取、JSON 转换、错误映射和事件输出。业务状态仍由 `QricsApiApp` 管理。

---

## 1. 设计边界

当前 API 的目标是在无数据库、无生产级消息总线、无前端控制台的条件下，让任务执行、控制状态、训练作业、策略治理、回放索引、审计记录和事件快照可测试、可演示。

约束：

- API 层不得接收或下发未经过安全语义建模的底层关节命令。
- API 层不暴露 MuJoCo、Isaac Lab、Webots 等后端内部对象。
- 进入仿真后端的动作必须是 `SafeAction`；被拒绝的 `SafeAction` 必须在后端命令映射阶段再次阻断。
- 高风险操作必须记录审计：急停、任务取消、策略发布、策略基线切换。
- 当前所有状态保存在进程内内存中，重启后丢失；持久化 repository、鉴权中间件和可靠消息总线属于后续阶段。
- 基础 `import qrics.api` 应保持无 FastAPI 依赖；需要 HTTP 服务时显式导入 `qrics.api.http_app` 或使用 `scripts/run_api_service.py`。

---

## 2. 运行入口

安装 API 依赖：

```bash
python -m pip install -e ".[api,dev]"
```

启动服务：

```bash
python scripts/run_api_service.py --host 127.0.0.1 --port 8000
```

开发自动重载：

```bash
python scripts/run_api_service.py --reload
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

---

## 3. 请求上下文

### 3.1 Facade `RequestContext`

Facade 调用显式携带 `RequestContext`。

| 字段 | 类型 | 说明 |
|---|---:|---|
| `request_id` | string | 请求 ID，用于串联 API 响应、事件和审计。 |
| `actor_id` | string | 操作者 ID。 |
| `role` | string | `operator`、`algorithm_engineer`、`test_engineer`、`admin`、`auditor`。 |

### 3.2 HTTP Header 映射

HTTP 层通过请求头生成 `RequestContext`。

| Header | 含义 | 默认值 |
|---|---|---|
| `x-request-id` | 端到端请求编号 | `req-http` |
| `x-actor-id` | 操作者 ID | `operator` |
| `x-actor-role` | 操作者角色 | `operator`，部分接口按用途设为 `algorithm_engineer` 或 `auditor` |

后续接入真实认证后，`actor_id` 与 `role` 应来自认证上下文，不应信任客户端任意传入。

---

## 4. 通用响应结构

Facade 返回 `ApiResponse`；HTTP 成功响应保留同一语义。

成功：

```json
{
  "ok": true,
  "data": {},
  "request_id": "req-demo-1"
}
```

失败：

```json
{
  "ok": false,
  "errors": [
    {"code": "NOT_FOUND", "message": "Task not found: task_999", "field": ""}
  ],
  "request_id": "req-demo-1"
}
```

错误对象：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `code` | string | 错误码，例如 `NOT_FOUND`、`CONFLICT`、`FORBIDDEN`、`INVALID_REQUEST`。 |
| `message` | string | 错误说明。 |
| `field` | string | 可选；参数错误对应字段。 |

HTTP 错误映射：

| API 错误码 | HTTP 状态码 |
|---|---:|
| `NOT_FOUND` | 404 |
| `FORBIDDEN` | 403 |
| `CONFLICT` | 409 |
| `INVALID_REQUEST` | 422 |
| 其他错误 | 500 |

---

## 5. Endpoint 总览

| 能力域 | HTTP / WS | Facade 方法 | 说明 |
|---|---|---|---|
| Health | `GET /api/v1/health` | transport only | 服务健康检查。 |
| Task | `POST /api/v1/tasks` | `submit_task` | 提交中文自然语言任务并生成执行预览。 |
| Task | `POST /api/v1/tasks/{task_id}/confirm` | `confirm_task` | 确认执行预览。 |
| Task | `POST /api/v1/tasks/{task_id}/handoff` | `handoff_task` | 将已确认任务交给控制运行。 |
| Task | `POST /api/v1/tasks/{task_id}/cancel` | `cancel_task` | 取消尚未 handoff 的任务。 |
| Control | `GET /api/v1/control/{run_id}` | `get_control_status` | 查询控制运行状态。 |
| Control | `POST /api/v1/control/{run_id}/override` | `override_control` | 急停、Safe-Stand、暂停、恢复或人工接管。 |
| Training | `POST /api/v1/training/plans` | `submit_training_plan` | 创建训练计划并进入 queued。 |
| Policy | `POST /api/v1/policies` | `register_policy` | 注册候选策略。 |
| Policy | `POST /api/v1/policies/gate-report` | `attach_gate_report` | 附加门禁结论。 |
| Policy | `POST /api/v1/policies/{policy_id}/{policy_version}/release` | `release_policy` | 发布已通过门禁的策略。 |
| Policy | `POST /api/v1/policies/{policy_id}/{policy_version}/baseline` | `promote_policy_baseline` | 提升策略为当前 baseline。 |
| Replay | `GET /api/v1/replay/{run_id}` | `query_replay` | 查询回放索引。 |
| Audit | `GET /api/v1/audit` | `query_audit` | 查询审计记录 ID。 |
| Events | `GET /api/v1/events?run_id=...` | `list_events` | 查询当前内存事件。 |
| Events | `WS /api/v1/ws/events?run_id=...` | `list_events` | WebSocket 事件快照。 |

---

## 6. Health API

### `GET /api/v1/health`

响应：

```json
{
  "ok": true,
  "service": "qrics-api",
  "version": "0.1.0"
}
```

---

## 7. Task API

### 7.1 `POST /api/v1/tasks`

提交自然语言任务，生成 `TaskPreviewResponse`。当前规则解析支持 `A`、`B`、`平台` 三类演示路径点。无法匹配路径点时，任务进入 `rejected`。

请求：

```json
{
  "source_text": "避开低摩擦区，先巡检A，再巡检B，最后回到平台待命",
  "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
  "require_confirmation": true
}
```

`scene_ref` 省略时默认：

```json
{"id": "minimal_scene", "version": "0.1.0"}
```

响应 `data`：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `task_id` | string | 任务 ID。 |
| `state` | string | `preview_ready` 或 `rejected`。 |
| `goal` | string | 原始任务文本。 |
| `waypoints` | array[string] | 解析出的路径点 ID。 |
| `selected_policy_reason` | string | 策略选择解释。 |
| `risk_summary` | string | 执行前风险说明。 |
| `operator_action_required` | boolean | 是否需要操作者确认。 |

示例响应：

```json
{
  "ok": true,
  "data": {
    "task_id": "task_1",
    "state": "preview_ready",
    "goal": "避开低摩擦区，先巡检A，再巡检B，最后回到平台待命",
    "waypoints": ["A", "B", "platform"],
    "selected_policy_reason": "规则策略选择：flat/gravel/platform 占位策略",
    "risk_summary": "未发现禁行区冲突；执行前仍需 Safety Shield 门控",
    "operator_action_required": true
  },
  "request_id": "req-demo-1"
}
```

### 7.2 `POST /api/v1/tasks/{task_id}/confirm`

只接受 `preview_ready` 状态任务。

响应 `data`：

```json
{
  "task_id": "task_1",
  "state": "confirmed",
  "event_count": 3,
  "latest_event": "confirmed"
}
```

### 7.3 `POST /api/v1/tasks/{task_id}/handoff`

只接受 `confirmed` 状态任务。handoff 后创建 `run_<task_id>` 控制运行，并通过本机 `SimulationRunner` 进行短步进演示。

响应 `data` 采用 `ControlStatusResponse`，见第 8 节。

### 7.4 `POST /api/v1/tasks/{task_id}/cancel`

请求：

```json
{"reason": "operator cancelled before handoff"}
```

约束：

- 可以取消 `preview_ready` 或 `confirmed` 状态任务。
- 不允许取消已经 `handed_off` 或 `cancelled` 的任务。
- 成功取消会追加 `task.cancel` 审计记录和 `audit.record` 事件。

### 7.5 任务状态流转

```text
submit_task -> preview_ready -> confirm_task -> confirmed -> handoff_task -> handed_off
submit_task -> rejected
preview_ready / confirmed -> cancel_task -> cancelled
```

---

## 8. Control API

### 8.1 `GET /api/v1/control/{run_id}`

查询控制运行状态。

`ControlStatusResponse.data`：

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

### 8.2 `POST /api/v1/control/{run_id}/override`

请求：

```json
{
  "command_type": "emergency_stop",
  "reason": "operator pressed stop"
}
```

| 字段 | 类型 | 说明 |
|---|---:|---|
| `command_type` | string | `emergency_stop`、`manual_control`、`safe_stand`、`pause`、`resume`。 |
| `reason` | string | 操作者或系统原因。 |

行为约束：

- `emergency_stop` 将运行置为 `paused`，最新动作为 `stop`，并追加 `control.emergency_stop` 审计记录。
- `safe_stand` 将运行置为 `paused`，最新动作为 `safe_stand`。
- `resume` 将运行置为 `running`。
- `manual_control` 与 `pause` 当前按暂停 / 停止语义处理，后续可扩展为人工接管状态机。
- 覆盖操作会追加 `control.alert` 事件。

---

## 9. Training API

### `POST /api/v1/training/plans`

请求：

```json
{
  "training_id": "train_1",
  "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
  "algorithm": "ppo_placeholder",
  "max_iterations": 100,
  "num_envs": 1,
  "seed": 42
}
```

| 字段 | 类型 | 默认值 | 说明 |
|---|---:|---|---|
| `training_id` | string | 无 | 训练计划 ID。 |
| `scene_ref` | object | `minimal_scene:0.1.0` | 场景引用。 |
| `algorithm` | string | `ppo_placeholder` | 算法名称。 |
| `max_iterations` | number | `100` | 最大迭代数，必须大于 0。 |
| `num_envs` | number | `1` | 并行环境数量，必须大于 0。 |
| `seed` | number | `42` | 随机种子。 |

当前 API 只创建 `queued` 作业，不执行真实强化学习训练。

响应 `data`：

```json
{
  "job_id": "job_train_1",
  "state": "queued",
  "scene_id": "minimal_scene",
  "scene_version": "0.1.0",
  "algorithm": "ppo_placeholder"
}
```

---

## 10. Policy API

### 10.1 `POST /api/v1/policies`

请求：

```json
{
  "policy_ref": {"id": "flat_nav", "version": "1.0.0"},
  "artifact_uri": "artifact://policies/flat_nav/1.0.0/model.pt",
  "checksum": "sha256:demo",
  "metrics": {
    "success_rate": 0.95,
    "collision_rate": 0.01,
    "tracking_error_m": 0.08,
    "recovery_rate": 0.90,
    "energy_proxy": 30.0,
    "hard_constraint_violation_count": 0
  }
}
```

响应 `data`：

```json
{
  "policy_id": "flat_nav",
  "policy_version": "1.0.0",
  "stage": "candidate",
  "is_current_baseline": false,
  "reason": ""
}
```

### 10.2 `POST /api/v1/policies/gate-report`

请求：

```json
{
  "policy_ref": {"id": "flat_nav", "version": "1.0.0"},
  "decision": "passed",
  "reason": "meets gate"
}
```

`decision` 允许值：`passed`、`failed`。

### 10.3 `POST /api/v1/policies/{policy_id}/{policy_version}/release`

请求：

```json
{"reason": "release after gate"}
```

约束：

- `x-actor-role` 必须是 `algorithm_engineer` 或 `admin`。
- 策略必须先通过 gate，才能 release。
- 发布成功后追加 `policy.release` 审计记录和 `audit.record` 事件。

### 10.4 `POST /api/v1/policies/{policy_id}/{policy_version}/baseline`

请求：

```json
{"reason": "promote as baseline"}
```

约束：

- `x-actor-role` 必须是 `algorithm_engineer` 或 `admin`。
- 只有 `released` 或已有 `baseline` 状态策略可以被提升为当前 baseline。
- 新 baseline 生效时，旧 baseline 回退为 `released`。
- 基线切换成功后追加 `policy.promote_baseline` 审计记录和 `audit.record` 事件。

策略状态机：

```text
candidate -> gate_passed -> released -> baseline
candidate -> gate_failed
baseline -> released   # 当新 baseline 被提升时，旧 baseline 回退为 released
```

---

## 11. Replay API

### `GET /api/v1/replay/{run_id}`

查询 API handoff 生成的回放索引。

可选查询参数：

| 参数 | 类型 | 说明 |
|---|---:|---|
| `event_type` | string | 预留过滤字段；当前实现不主动按事件类型裁剪。 |

响应 `data`：

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

---

## 12. Audit API

### `GET /api/v1/audit`

查询审计记录 ID。

查询参数：

| 参数 | 类型 | 说明 |
|---|---:|---|
| `actor_id` | string | 按操作者过滤。 |
| `object_id` | string | 按对象 ID 过滤。 |
| `action` | string | 按动作过滤，例如 `control.emergency_stop`、`policy.release`。 |

响应 `data`：

```json
{
  "count": 1,
  "audit_ids": ["audit_1"]
}
```

当前只返回审计 ID 列表；后续服务化阶段应增加分页、时间范围、角色过滤和完整记录读取接口。

---

## 13. Event API

### 13.1 `GET /api/v1/events`

查询进程内事件流。

查询参数：

| 参数 | 类型 | 说明 |
|---|---:|---|
| `run_id` | string | 可选；按运行 ID 过滤。 |

响应：

```json
{
  "count": 1,
  "events": [
    {
      "event_id": "event_3",
      "topic": "control.status",
      "run_id": "run_task_1",
      "message": "Control run started",
      "payload": {
        "run_id": "run_task_1",
        "state": "running",
        "backend": "minimal",
        "runtime_profile": "headless_fast",
        "control_step_count": 20,
        "base_position": [0.05, 0.0, 0.32],
        "sim_time_ns": 800000000
      },
      "request_id": "req-demo-1"
    }
  ]
}
```

### 13.2 `WS /api/v1/ws/events?run_id=<run_id>`

WebSocket 事件快照。服务端会发送当前匹配事件，然后发送 `snapshot_complete` 标记。

`snapshot_complete`：

```json
{
  "event_id": "snapshot_complete",
  "topic": "control.status",
  "run_id": "run_task_1",
  "message": "event snapshot complete",
  "payload": {"count": 1},
  "request_id": "ws"
}
```

客户端发送以下消息后，服务端关闭连接：

```json
{"op": "close"}
```

事件主题、事件信封和 payload 约束详见 [`docs/api/events.md`](events.md)。

---

## 14. 仿真后端选择

当前 HTTP 层未直接开放后端选择字段；`QricsApiApp` 通过以下默认值驱动本机 `SimulationRunner`：

```text
backend = minimal
runtime_profile = headless_fast
```

API 响应和事件中必须暴露后端选择与运行档位，避免不同仿真后端结果混用。

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

---

## 15. HTTP / WebSocket 实现原则

1. 不修改 `schemas.py` 的业务字段语义。
2. 不把 HTTP handler 写成业务逻辑承载层；handler 只做请求上下文提取、请求体转换、调用 facade、响应序列化。
3. `ApiResponse.ok=false` 映射到合适 HTTP 状态码，但错误码仍保留在响应体中。
4. 高风险操作的 `reason` 字段必须保留，不能由 HTTP 层丢弃。
5. WebSocket 推送使用 `EventEnvelope`，不得以临时前端字段替代正式事件信封。
6. 事件与审计 payload 不得包含 token、密钥、对象存储凭据、模型签名私钥或本机绝对路径。
7. 基础 `qrics.api` 包必须保持可在未安装 `api` extra 时导入；FastAPI 相关对象应保留在 `qrics.api.http_app` 中按需导入。

---

## 16. 当前限制与后续工作

当前限制：

- HTTP / WebSocket 服务已可运行，但业务状态仍为进程内内存，重启后丢失。
- WebSocket 当前是连接时刻事件快照，不是生产级增量消息总线。
- 当前没有真实认证中间件；`x-actor-role` 仍是演示用请求头。
- 训练 API 只进入 `queued`，不执行真实强化学习训练。
- Isaac Lab 真实运行环境闭环仍待开发；当前 HTTP handoff 默认使用 `minimal` 本机后端。
- 前端控制台尚未实现。

后续工作：

- 增加持久化 repository，落地任务、控制运行、训练作业、策略状态、回放索引和审计记录。
- 接入真实 Auth Middleware / RBAC。
- 接入可靠消息总线并把 WebSocket 从快照扩展为增量订阅。
- 补充任务取消、override、training plan、baseline、audit 查询等 HTTP 端点测试。
- 将 Isaac Lab Adapter 真实运行闭环接入同一 Simulation Adapter 语义。