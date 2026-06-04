# QRICS API 事件契约

本文档定义 QRICS 应用接口层使用的事件主题、事件信封、HTTP 查询、WebSocket 快照和 RBAC / Audit 约束。当前实现由 `QricsApiApp` 与 repository 维护事件，并由 `qrics.api.http_app` 暴露：

- `GET /api/v1/events?run_id=...`
- `WS /api/v1/ws/events?run_id=...`

事件语义应在后续接入 Redis Streams、Kafka、数据库审计表或生产级 WebSocket 增量推送时保持兼容。

---

## 1. 适用边界

事件流用于展示和追踪以下链路：

```text
场景创建/发布 -> 任务提交 -> 执行预览 -> 操作者确认 -> 控制 handoff -> 仿真短步进 -> 状态事件 -> 回放索引 -> 高风险操作 -> 审计事件
```

当前事件流已经具备 HTTP 查询和 WebSocket 快照能力，但不承担跨进程可靠投递、断线续传或生产级消息总线职责。

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
| `timestamp_ns` | integer | 是 | 服务端事件写入时间戳，纳秒。 |

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
  "request_id": "req-1",
  "timestamp_ns": 1710000000000000000
}
```

---

## 3. 主题总览

| topic | 生产者 | 典型触发 | 主要用途 |
|---|---|---|---|
| `scene.lifecycle` | Scene API | `create_scene`、`copy_scene`、`publish_scene_baseline`、`archive_scene` | 展示场景创建、复制、基线发布和归档。 |
| `task.lifecycle` | Task API | `submit_task`、`confirm_task`、`handoff_task` | 展示任务提交、预览生成、操作者确认和任务交接。 |
| `control.status` | Control API | `handoff_task` | 展示控制运行启动、仿真后端、运行档位和最新状态。 |
| `control.alert` | Control API | `override_control` | 展示急停、Safe-Stand、暂停、恢复、人工接管等控制覆盖事件。 |
| `training.status` | Training / Evaluation API | `submit_training_plan`、`start_training_job`、`record_training_checkpoint`、`complete_training_job`、`fail_training_job`、`cancel_training_job`、`run_standard_evaluation` | 展示训练作业队列、运行、检查点、完成、失败、取消和标准化评测状态变化。 |
| `policy.lifecycle` | Policy / Evaluation API | `register_policy`、`attach_gate_report`、`complete_training_job`、`run_standard_evaluation` | 展示候选策略注册、训练产物注册、门禁状态变化和策略评测结果。 |
| `replay.index` | Replay Service | 后续关键帧或回放片段写入 | 展示关键帧索引和回放清单更新。当前 HTTP Facade 查询回放索引但不主动发布该事件。 |
| `audit.record` | Audit Service | 权限失败、缺少原因、任务取消、控制覆盖、策略注册、门禁、发布、基线切换等 | 展示追加式审计记录生成。 |

---

## 4. RBAC / Audit 事件约束

- 权限失败会生成 `audit.record` 事件，事件 payload 中的 `result` 为 `denied`。
- 高风险操作缺少原因时会生成 `audit.record` 事件，事件 payload 中的 `result` 为 `rejected`。
- 高风险业务前置条件不满足时，例如门禁未通过发布策略，会生成 `audit.record` 事件，`result=rejected`。
- 高风险操作成功时会生成 `audit.record` 事件，事件 payload 中的 `result` 为 `success`。
- 场景基线发布和场景归档同时生成 `scene.lifecycle` 与 `audit.record`，用于串联场景版本状态和审批原因。
- WebSocket 事件快照完成消息必须携带 `timestamp_ns`，与普通事件信封保持一致。
- WebSocket `/api/v1/ws/events` 使用与 HTTP API 相同的非提权上下文规则。缺省上下文等价于 `operator`，可以读取事件快照，但不会隐式提升为 `auditor`。可通过 query 参数传入 `request_id`、`actor_id`、`actor_role` 形成演示上下文。
- `GET /api/v1/events` 统一返回 `ApiResponse` 封装：`data.count` 与 `data.events`。

---

## 5. 主题 payload 约束


### 5.0 `scene.lifecycle`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `scene_id` | string | 场景 ID。 |
| `scene_version` | string | 场景版本。 |
| `state` | string | `draft`、`published`、`archived`。 |
| `is_current_baseline` | boolean | 是否为当前基线版本。 |
| `checksum` | string | 场景配置包摘要。 |
| `reason` | string | 发布、复制或归档原因。 |

### 5.1 `task.lifecycle`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `task_id` | string | 任务 ID，例如 `task_1`。 |
| `state` | string | `preview_ready`、`rejected`、`confirmed`、`handed_off`、`cancelled`。 |

### 5.2 `control.status`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `run_id` | string | 控制运行 ID，例如 `run_task_1`。 |
| `state` | string | `created`、`running`、`paused`、`succeeded`、`failed`、`cancelled`。 |
| `backend` | string | `minimal`、`mujoco`、`webots`、`isaac_lab` 等后端标识。 |
| `runtime_profile` | string | `headless_fast`、`balanced_visual`、`rich_demo`。 |
| `control_step_count` | number | 本次 handoff 已执行控制步数。 |
| `base_position` | array[number] | 机器人 base 位置 `[x, y, z]`。 |
| `sim_time_ns` | number | 仿真时间戳。 |
| `replay_manifest_uri` | string | 回放清单 URI。 |

### 5.3 `control.alert`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `run_id` | string | 控制运行 ID。 |
| `state` | string | 覆盖后的运行状态，通常为 `paused` 或 `running`。 |
| `action` | string | 覆盖后的安全动作，例如 `stop`、`safe_stand`、`body_velocity`。 |
| `backend` | string | 当前仿真后端。 |
| `runtime_profile` | string | 当前运行档位。 |

### 5.4 `training.status`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `job_id` | string | 训练作业 ID，例如 `job_train_1`。 |
| `state` | string | `queued`、`running`、`succeeded`、`failed`、`cancelled`。 |
| `scene_id` | string | 场景 ID。 |
| `scene_version` | string | 场景版本。 |
| `algorithm` | string | 算法名称。 |
| `max_iterations` | integer | 训练计划最大迭代数。 |
| `current_iteration` | integer | 当前迭代数。 |
| `checkpoint_count` | integer | 已记录检查点数量。 |
| `latest_checkpoint_uri` | string | 最近检查点 URI。 |
| `config_hash` | string | 训练配置确定性摘要。 |
| `decision` | string | 评测事件中可出现，表示 `passed` 或 `failed`。 |

### 5.5 `policy.lifecycle`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `policy_id` | string | 策略 ID。 |
| `policy_version` | string | 策略版本。 |
| `stage` | string | `candidate`、`gate_passed`、`gate_failed`、`released`、`baseline`、`archived`。 |
| `is_current_baseline` | boolean | 是否为当前 baseline。 |
| `reason` | string | 状态说明或审批原因。 |
| `artifact_uri` | string | 策略工件 URI。 |
| `checksum` | string | 策略工件校验和。 |
| `metrics` | object | 成功率、碰撞率、轨迹误差、恢复率、能耗代理与硬约束违规数。 |

### 5.6 `audit.record`

| 字段 | 类型 | 说明 |
|---|---:|---|
| `audit_id` | string | 审计记录 ID。 |
| `actor_id` | string | 操作者 ID。 |
| `actor_role` | string | 操作者角色。 |
| `action` | string | 动作名称，例如 `control.emergency_stop`、`policy.release`。 |
| `object_id` | string | 目标对象 ID。 |
| `object_version` | string | 目标对象版本。 |
| `result` | string | `success`、`denied`、`rejected`、`failed`。 |
| `reason` | string | 操作原因或拒绝原因。 |
| `request_id` | string | 请求链路编号。 |
| `timestamp_ns` | integer | 审计写入时间戳。 |

---

## 6. HTTP 事件查询

当前 HTTP 事件查询入口：

```text
GET /api/v1/events?run_id=<run_id>
```

请求头：

| Header | 含义 | 默认值 |
|---|---|---|
| `x-request-id` | 端到端请求编号 | `req-http` |
| `x-actor-id` | 操作者 ID | `operator` |
| `x-actor-role` | 操作者角色 | `operator` |

当前查询支持按 `run_id` 过滤。返回结构：

```json
{
  "ok": true,
  "data": {
    "count": 1,
    "events": [
      {
        "event_id": "event_3",
        "topic": "control.status",
        "run_id": "run_task_1",
        "message": "Control run started",
        "payload": {},
        "request_id": "req-demo-1",
        "timestamp_ns": 1710000000000000000
      }
    ]
  },
  "request_id": "req-demo-1"
}
```

---

## 7. WebSocket 事件快照接口

```text
WS /api/v1/ws/events?run_id=<run_id>
WS /api/v1/ws/events?run_id=<run_id>&request_id=req-ws-1&actor_id=operator-1&actor_role=operator
```

连接建立后，服务端按连接 header 或查询参数生成 `RequestContext`，使用与 HTTP 事件查询相同的 `events.read` 权限路径读取当前 `run_id` 过滤下的事件快照，然后发送 `snapshot_complete`。未提供上下文时默认角色为 `operator`；未知角色会在 WebSocket 内返回 `INVALID_REQUEST` 后关闭连接。

```json
{
  "event_id": "snapshot_complete",
  "topic": "control.status",
  "run_id": "run_task_1",
  "message": "event snapshot complete",
  "payload": {"count": 1},
  "request_id": "req-ws-1",
  "timestamp_ns": 1710000000000000000
}
```

当前 WebSocket 仍是快照接口，不是生产级增量订阅通道；传输层不再硬编码 auditor 上下文。