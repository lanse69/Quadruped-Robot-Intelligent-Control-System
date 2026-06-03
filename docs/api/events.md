# QRICS API 事件契约

本文档定义 QRICS 应用接口层使用的事件主题、事件信封、HTTP 查询和 WebSocket 快照约束。当前实现由 `QricsApiApp` 与 `InMemoryEventStream` 维护进程内事件，并由 `qrics.api.http_app` 暴露：

- `GET /api/v1/events?run_id=...`
- `WS /api/v1/ws/events?run_id=...`

事件语义应在后续接入 Redis Streams、Kafka、数据库审计表或生产级 WebSocket 增量推送时保持兼容。

---

## 1. 适用边界

事件流用于展示和追踪以下链路：

```text
任务提交 -> 执行预览 -> 操作者确认 -> 控制 handoff -> 仿真短步进 -> 状态事件 -> 回放索引 -> 急停/审计
```

当前事件流已经具备 HTTP 查询和真实 WebSocket 连接，但仍是单进程内存实现，不承担跨进程可靠投递、长期留存、事件级 RBAC、断线续传或生产级消息总线职责。持久化、鉴权、订阅过滤和导出应由后续 repository、Auth Middleware、消息总线和审计服务实现。

---

## 2. 事件信封

所有事件统一使用 `EventEnvelope`。

| 字段 | 类型 | 必填 | 说明 |
|---|---:|---:|---|
| `event_id` | string | 是 | 事件流内递增生成的事件 ID，当前格式为 `event_N`。WebSocket 快照结束标记使用 `snapshot_complete`。 |
| `topic` | string | 是 | 事件主题，取值见第 3 节。 |
| `run_id` | string | 否 | 控制运行、训练作业或任务运行的关联 ID；无运行上下文时为空字符串。 |
| `message` | string | 是 | 面向日志和演示输出的短消息，不作为状态机唯一事实源。 |
| `payload` | object | 是 | 主题相关字段。不得写入 token、密钥、对象存储凭据或模型签名私钥。 |
| `request_id` | string | 是 | 调用 API 或 WebSocket 快照时的请求 ID，用于串联请求、事件和审计。 |

事件信封示例：

```json
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
  "request_id": "req-1"
}
```

---

## 3. 主题总览

| topic | 生产者 | 典型触发 | 主要用途 |
|---|---|---|---|
| `task.lifecycle` | Task API | `submit_task`、`confirm_task` | 展示任务提交、预览生成、操作者确认等生命周期变化。 |
| `control.status` | Control API | `handoff_task` | 展示控制运行启动、仿真后端、运行档位和最新状态。 |
| `control.alert` | Control API | `override_control` | 展示急停、Safe-Stand、暂停、恢复、人工接管等控制覆盖事件。 |
| `training.status` | Training API | `submit_training_plan` | 展示训练作业进入队列或后续训练状态变化。 |
| `policy.lifecycle` | Policy API | `register_policy` | 展示候选策略注册状态。当前 gate、release、baseline 主要通过响应和审计表达，后续可追加该主题事件。 |
| `replay.index` | Replay Service | 后续关键帧或回放片段写入 | 展示关键帧索引和回放清单更新。当前 HTTP Facade 查询回放索引但不主动发布该事件。 |
| `audit.record` | Audit Service | 任务取消、急停、策略发布、基线切换等高风险动作 | 展示追加式审计记录生成。 |

---

## 4. 主题 payload 约束

### 4.1 `task.lifecycle`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `task_id` | string | 任务 ID，例如 `task_1`。 |
| `state` | string | `preview_ready`、`rejected`、`confirmed`、`handed_off`、`cancelled`。 |

示例：

```json
{
  "task_id": "task_1",
  "state": "preview_ready"
}
```

### 4.2 `control.status`

本机仿真后端接入后，`control.status` 必须携带仿真上下文字段，避免把 Minimal 契约测试、MuJoCo 本机物理演示和后续 Isaac Lab 高保真运行结果混用。

| 字段 | 类型 | 说明 |
|---|---:|---|
| `run_id` | string | 控制运行 ID，例如 `run_task_1`。 |
| `state` | string | `created`、`running`、`paused`、`succeeded`、`failed`、`cancelled`。 |
| `backend` | string | `minimal`、`mujoco`、`webots`、`isaac_lab` 等后端标识。 |
| `runtime_profile` | string | `headless_fast`、`balanced_visual`、`rich_demo`。 |
| `control_step_count` | number | 本次 handoff 已执行控制步数。 |
| `base_position` | array[number] | 机器人 base 位置 `[x, y, z]`。 |
| `sim_time_ns` | number | 仿真时间戳。 |

示例：

```json
{
  "run_id": "run_task_1",
  "state": "running",
  "backend": "minimal",
  "runtime_profile": "headless_fast",
  "control_step_count": 20,
  "base_position": [0.05, 0.0, 0.32],
  "sim_time_ns": 800000000
}
```

### 4.3 `control.alert`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `run_id` | string | 控制运行 ID。 |
| `state` | string | 覆盖后的运行状态，通常为 `paused` 或 `running`。 |
| `action` | string | 覆盖后的安全动作，例如 `stop`、`safe_stand`、`body_velocity`。 |
| `backend` | string | 当前仿真后端。 |
| `runtime_profile` | string | 当前运行档位。 |

示例：

```json
{
  "run_id": "run_task_1",
  "state": "paused",
  "action": "stop",
  "backend": "minimal",
  "runtime_profile": "headless_fast"
}
```

### 4.4 `training.status`

当前训练 API 只创建 `queued` 作业，不执行真实强化学习训练。

| 字段 | 类型 | 说明 |
|---|---:|---|
| `job_id` | string | 训练作业 ID，例如 `job_train_1`。 |
| `state` | string | `queued`、`running`、`succeeded`、`failed`、`cancelled`。 |
| `scene_id` | string | 场景 ID。 |
| `scene_version` | string | 场景版本。 |
| `algorithm` | string | 算法名称。 |

### 4.5 `policy.lifecycle`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `policy_id` | string | 策略 ID。 |
| `policy_version` | string | 策略版本。 |
| `stage` | string | `candidate`、`gate_passed`、`gate_failed`、`released`、`baseline`、`archived`。 |
| `is_current_baseline` | boolean | 是否为当前 baseline。 |
| `reason` | string | 状态说明或审批原因。 |

### 4.6 `replay.index`

当前实现中的回放索引通过 `GET /api/v1/replay/{run_id}` 查询；后续如果主动发布 `replay.index`，payload 应与 `ReplayResponse` 摘要保持一致。

| 字段 | 类型 | 说明 |
|---|---:|---|
| `run_id` | string | 控制运行 ID。 |
| `segment_count` | number | 回放片段数量。 |
| `keyframe_count` | number | 关键帧数量。 |
| `backend` | string | 回放对应后端。 |
| `runtime_profile` | string | 回放对应运行档位。 |
| `first_timestamp_ns` | number | 回放时间窗起点。 |
| `last_timestamp_ns` | number | 回放时间窗终点。 |
| `keyframes` | array[string] | 关键帧 ID 列表。 |

### 4.7 `audit.record`

`audit.record` 是高风险动作的事件化摘要，不替代后续持久化审计表。

| 字段 | 类型 | 说明 |
|---|---:|---|
| `audit_id` | string | 审计记录 ID。 |
| `actor_id` | string | 操作者 ID。 |
| `action` | string | 动作名称，例如 `task.cancel`、`control.emergency_stop`、`policy.release`、`policy.promote_baseline`。 |
| `object_id` | string | 目标对象 ID。 |
| `object_version` | string | 目标对象版本。 |
| `result` | string | `success`、`failed` 等结果。 |
| `reason` | string | 操作原因。 |

示例：

```json
{
  "audit_id": "audit_1",
  "actor_id": "operator-1",
  "action": "control.emergency_stop",
  "object_id": "run_task_1",
  "object_version": "",
  "result": "success",
  "reason": "operator pressed stop"
}
```

---

## 5. HTTP 事件查询

当前 HTTP 事件查询入口：

```text
GET /api/v1/events?run_id=<run_id>
```

请求头：

| Header | 含义 | 默认值 |
|---|---|---|
| `x-request-id` | 端到端请求编号 | `req-http` |
| `x-actor-id` | 操作者 ID | `operator` |
| `x-actor-role` | 操作者角色 | `auditor` |

当前查询只支持按 `run_id` 过滤。返回结构：

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

---

## 6. WebSocket 事件快照接口

当前 WebSocket 入口：

```text
WS /api/v1/ws/events?run_id=<run_id>
```

服务端行为：

1. 接受 WebSocket 连接。
2. 读取当前内存事件流中匹配 `run_id` 的事件。
3. 按事件信封逐条发送 JSON。
4. 发送 `snapshot_complete` 标记。
5. 等待客户端消息；收到 `{"op":"close"}` 后关闭连接。

`snapshot_complete` 示例：

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

客户端关闭消息：

```json
{"op": "close"}
```

当前 WebSocket 是事件快照通道，不是生产级增量订阅。后续接入消息总线时，应保持事件信封字段稳定，并把快照能力扩展为增量推送、断线续传和事件级权限过滤。

---

## 7. 事件生产规则

1. 事件追加后不得原地修改；修正状态应追加新事件。
2. `request_id` 必须贯穿 API 响应、事件和审计记录。
3. 控制类事件必须带 `run_id`；训练类事件使用 `job_id` 作为 `run_id`。
4. `control.status` 和 `control.alert` 必须保留 `backend` 与 `runtime_profile`。
5. 高风险动作必须同时产生业务响应和 `audit.record`；审计事件不替代后续持久化审计存储。
6. WebSocket 和未来消息总线推送不得让控制台以高频轮询占用控制链路。
7. 事件 payload 不得包含 token、密钥、对象存储凭据、模型签名私钥或本机绝对路径。

---

## 8. 当前限制与后续演进

当前限制：

- 事件只保存在进程内内存中，服务重启后清空。
- WebSocket 已提供真实连接，但当前只发送连接时刻的事件快照，不提供持续增量推送。
- 不保证跨进程持久化、可靠投递、断线续传和历史重放。
- 不提供事件级 RBAC 过滤；当前通过请求头模拟 `RequestContext`。

后续演进要求：

- 保留 `topic`、`run_id`、`request_id`、`backend`、`runtime_profile` 的语义。
- 新增字段必须向后兼容，不得破坏既有 API Facade、HTTP API 和 WebSocket 测试。
- 持久化事件、审计表和对象存储引用应通过不可变 ID 或版本摘要串联。