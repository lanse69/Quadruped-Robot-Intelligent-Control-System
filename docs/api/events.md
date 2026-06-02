# QRICS 事件主题草案 v0.1

当前阶段使用 `InMemoryEventStream` 模拟后续 WebSocket / 消息总线。事件用于答辩时展示任务状态、控制状态、训练状态、模型治理和审计证据链。

## 1. 事件信封

事件统一使用 `EventEnvelope`：

```text
event_id
topic
run_id
message
payload
request_id
```

## 2. 主题

| topic | 生产者 | 典型触发 | 用途 |
|---|---|---|---|
| `task.lifecycle` | Task API | submit / confirm | 展示任务提交、预览、确认状态 |
| `control.status` | Control API | handoff | 展示控制运行启动和状态刷新 |
| `control.alert` | Control API | emergency_stop / safe_stand / manual_control | 展示急停、安全站立、人工接管 |
| `training.status` | Training API | submit_training_plan | 展示训练作业进入队列 |
| `policy.lifecycle` | Policy API | register / release / baseline | 展示策略状态变化 |
| `replay.index` | Replay API | 后续关键帧写入 | 展示回放索引更新 |
| `audit.record` | Audit API | 高风险操作 | 展示审计证据 |

## 仿真后端状态事件

本机 MuJoCo 后端接入后，控制状态事件应携带仿真后端和运行档位，便于回放和审计时判断运行环境。

建议字段：

```json
{
  "topic": "control.status",
  "backend": "mujoco",
  "runtime_profile": "balanced_visual",
  "run_id": "run_xxx",
  "state": "running",
  "risk_score": 0.0
}
```

如果后续同一任务在 Isaac Lab、MuJoCo、Webots 中重复运行，事件流必须保留 `backend` 字段，避免混淆不同仿真平台的性能和物理结果。

## 3. 当前限制

- 当前事件仅在内存中保存。
- 当前不提供真实 WebSocket 连接。
- 当前不保证跨进程持久化。
- 后续接入消息总线时必须保留 `topic`、`run_id`、`request_id` 三个字段。