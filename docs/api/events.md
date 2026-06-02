# QRICS API 事件契约 v0.2

本文档定义 `python/qrics/api` 应用 Facade 当前使用的事件主题、事件信封和 payload 约束。当前实现使用 `InMemoryEventStream` 支撑单进程测试与本机演示；后续接入 WebSocket、Redis Streams、Kafka 或数据库审计表时，事件语义必须保持兼容。

## 1. 适用边界

事件流用于展示和追踪以下链路：

```text
任务提交 -> 执行预览 -> 操作者确认 -> 控制 handoff -> 仿真短步进 -> 状态事件 -> 回放索引 -> 急停/审计
```

当前事件流不是生产级消息总线，不承担跨进程可靠投递、长期留存或权限过滤。持久化、鉴权和导出应由后续服务化适配层实现。

## 2. 事件信封

所有事件统一使用 `EventEnvelope`。

| 字段 | 类型 | 必填 | 说明 |
|---|---:|---:|---|
| `event_id` | string | 是 | 事件流内递增生成的事件 ID，当前格式为 `event_N`。 |
| `topic` | string | 是 | 事件主题，取值见第 3 节。 |
| `run_id` | string | 否 | 控制运行、训练作业或任务运行的关联 ID；无运行上下文时为空字符串。 |
| `message` | string | 是 | 面向日志和演示输出的短消息，不作为状态机唯一事实源。 |
| `payload` | object | 是 | 主题相关字段。不得写入 token、密钥、对象存储凭据或模型签名私钥。 |
| `request_id` | string | 是 | 调用 API Facade 时传入的请求 ID，用于串联请求、事件和审计。 |

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

## 3. 主题总览

| topic | 生产者 | 典型触发 | 主要用途 |
|---|---|---|---|
| `task.lifecycle` | Task API | `submit_task`、`confirm_task` | 展示任务提交、预览生成、确认等生命周期变化。 |
| `control.status` | Control API | `handoff_task` | 展示控制运行启动、仿真后端、运行档位和最新状态。 |
| `control.alert` | Control API | `override_control` | 展示急停、Safe-Stand、暂停、恢复、人工接管等控制覆盖事件。 |
| `training.status` | Training API | `submit_training_plan` | 展示训练作业进入队列或后续训练状态变化。 |
| `policy.lifecycle` | Policy API | `register_policy`、`release_policy`、`promote_policy_baseline` | 展示候选策略、门禁、发布和基线切换状态。 |
| `replay.index` | Replay Service | 后续关键帧或回放片段写入 | 展示关键帧索引和回放清单更新。当前 Facade 查询回放索引但不主动发布该事件。 |
| `audit.record` | Audit Service | 任务取消、急停、策略发布、基线切换等高风险动作 | 展示追加式审计记录生成。 |

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
| `backend` | string | `minimal`、`mujoco`、`webots`、`isaac_lab`。当前 API 演示默认 `minimal`。 |
| `runtime_profile` | string | `headless_fast`、`balanced_visual`、`rich_demo`。当前 API 演示默认 `headless_fast`。 |
| `control_step_count` | number | 本次 handoff 后端实际执行的控制步数。 |
| `base_position` | array[number] | 机器人 base 位置 `[x, y, z]`，单位为米。 |
| `sim_time_ns` | number | 后端返回的仿真时间戳，单位为纳秒。 |
| `risk_score` | number | 可选；风险分数，缺省可由 `ControlStatusResponse` 提供。 |

示例：

```json
{
  "run_id": "run_task_1",
  "state": "running",
  "backend": "mujoco",
  "runtime_profile": "headless_fast",
  "control_step_count": 20,
  "base_position": [0.024, 0.0, 0.280],
  "sim_time_ns": 400000000,
  "risk_score": 0.0
}
```

### 4.3 `control.alert`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `run_id` | string | 控制运行 ID。 |
| `state` | string | 覆盖命令应用后的控制状态。 |
| `action` | string | 最新安全动作，例如 `stop`、`safe_stand`。 |
| `backend` | string | 触发告警时的仿真后端。 |
| `runtime_profile` | string | 触发告警时的运行档位。 |
| `reason` | string | 可选；操作者或系统给出的原因。 |

急停示例：

```json
{
  "run_id": "run_task_1",
  "state": "paused",
  "action": "stop",
  "backend": "minimal",
  "runtime_profile": "headless_fast",
  "reason": "答辩急停演示"
}
```

### 4.4 `training.status`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `job_id` | string | 训练作业 ID。 |
| `state` | string | `queued`、`running`、`succeeded`、`failed`、`cancelled`。 |
| `scene_id` | string | 场景 ID。 |
| `scene_version` | string | 场景版本。 |
| `algorithm` | string | 算法名称，例如 `ppo_placeholder`。 |

### 4.5 `policy.lifecycle`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `policy_id` | string | 策略 ID。 |
| `policy_version` | string | 策略版本。 |
| `stage` | string | `draft`、`candidate`、`gate_passed`、`gate_failed`、`released`、`baseline`、`archived`。 |
| `is_current_baseline` | boolean | 是否为当前执行基线。 |
| `reason` | string | 状态变化原因。 |

### 4.6 `replay.index`

后续接入回放写入器后使用。当前 `query_replay` 返回 `ReplayResponse`，但不要求每次查询都发布事件。

| 字段 | 类型 | 说明 |
|---|---:|---|
| `run_id` | string | 运行 ID。 |
| `backend` | string | 回放片段对应的仿真后端。 |
| `runtime_profile` | string | 回放片段对应的运行档位。 |
| `segment_count` | number | 回放片段数量。 |
| `keyframe_count` | number | 关键帧数量。 |
| `first_timestamp_ns` | number | 回放时间窗起点。 |
| `last_timestamp_ns` | number | 回放时间窗终点。 |

### 4.7 `audit.record`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `audit_id` | string | 审计记录 ID。 |
| `actor_id` | string | 操作者 ID。 |
| `action` | string | 高风险动作，例如 `control.emergency_stop`、`policy.release`。 |
| `object_id` | string | 被操作对象 ID。 |
| `object_version` | string | 被操作对象版本。 |
| `result` | string | `success`、`failed` 等结果。 |
| `reason` | string | 操作原因。 |

## 5. 事件生产规则

1. 事件追加后不得原地修改；修正状态应追加新事件。
2. `request_id` 必须贯穿 API 响应、事件和审计记录。
3. 控制类事件必须带 `run_id`；训练类事件使用 `job_id` 作为 `run_id`。
4. `control.status` 和 `control.alert` 必须保留 `backend` 与 `runtime_profile`。
5. 高风险动作必须同时产生业务响应和 `audit.record`；审计事件不替代审计存储。
6. 后续 WebSocket 推送不得让控制台以高频轮询占用控制链路。

## 6. 当前限制与后续演进

当前限制：

- 事件只保存在内存中。
- 未提供真实 WebSocket 连接。
- 不保证跨进程持久化和重放。
- 不提供事件级 RBAC 过滤。

后续接入服务化适配层时必须保留 `topic`、`run_id`、`request_id`、`backend`、`runtime_profile` 的语义。新增字段应向后兼容，不得破坏既有 Facade 测试。