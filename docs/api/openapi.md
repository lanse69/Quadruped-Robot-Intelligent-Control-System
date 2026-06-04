# QRICS HTTP API / API Facade 契约

本文档描述 QRICS 应用接口族、请求/响应结构、HTTP 映射、RBAC 门控、事件查询和 WebSocket 快照接口。当前仓库提供两层 API：

1. `python/qrics/api/app.py`：依赖标准库的 `QricsApiApp` 应用 Facade，承载任务、控制、训练、策略、回放、审计和事件流的业务边界。
2. `python/qrics/api/http_app.py`：可选 FastAPI / WebSocket 传输适配层，暴露 `/api/v1` HTTP 接口和 `/api/v1/ws/events` WebSocket 事件快照。

HTTP 层不得承载领域规则；它只负责请求上下文提取、JSON 转换、错误映射和事件输出。权限、状态流转和高风险操作审计由 `QricsApiApp` 统一处理。

---

## 1. 设计边界

当前 API 的目标是在本机环境内让任务执行、控制状态、训练作业、策略治理、回放索引、审计记录和事件快照可测试、可演示、可追溯。

约束：

- API 层不得接收或下发未经过安全语义建模的底层关节命令。
- API 层不暴露 MuJoCo、Isaac Lab、Webots 等后端内部对象。
- 进入仿真后端的动作必须是经过 Safety Shield 语义约束后的安全动作。
- 训练、策略治理、审计查询等接口默认不授予高权限；调用方必须显式声明角色。
- 高风险操作的成功、权限失败和业务拒绝路径必须写入追加式审计记录。
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

## 3. 请求上下文与 RBAC

### 3.1 Facade `RequestContext`

Facade 调用显式携带 `RequestContext`。

| 字段 | 类型 | 说明 |
|---|---:|---|
| `request_id` | string | 请求 ID，用于串联 API 响应、事件和审计。 |
| `actor_id` | string | 操作者 ID。 |
| `role` | string | `operator`、`algorithm_engineer`、`test_engineer`、`auditor`、`admin`。 |

### 3.2 HTTP Header 映射

HTTP 层通过请求头生成 `RequestContext`。

| Header | 含义 | 默认值 |
|---|---|---|
| `x-request-id` | 端到端请求编号 | `req-http` |
| `x-actor-id` | 操作者 ID | `operator` |
| `x-actor-role` | 操作者角色 | `operator` |

后续接入真实认证后，`actor_id` 与 `role` 应来自认证上下文，不应信任客户端任意传入。

### 3.3 角色权限矩阵

| 角色 | 主要权限 |
|---|---|
| `operator` | 任务提交、确认、交接、取消；控制状态读取；急停、Safe-Stand、人工接管、暂停、恢复；回放和事件读取。 |
| `algorithm_engineer` | 训练计划提交、策略注册、门禁报告、策略发布、基线切换；控制状态、回放和事件读取。 |
| `test_engineer` | 任务执行、控制安全操作、回放和事件读取。 |
| `auditor` | 审计查询、事件查询、回放查询和控制状态读取。 |
| `admin` | 当前所有应用层权限。 |

默认拒绝规则：未知角色或缺失权限时返回 `403 FORBIDDEN`，并追加审计记录，`result=denied`。

### 3.4 高风险操作门控

| action | 要求 |
|---|---|
| `task.cancel` | 需要权限和非空 `reason`。 |
| `control.emergency_stop` | 需要权限；不强制原因，避免阻塞急停路径。 |
| `control.safe_stand` | 需要权限；不强制原因。 |
| `control.manual_control` | 需要权限和非空 `reason`。 |
| `control.pause` | 需要权限；不强制原因。 |
| `control.resume` | 需要权限；不强制原因。 |
| `policy.gate_report` | 需要权限和非空 `reason`。 |
| `policy.release` | 需要权限和非空 `reason`。 |
| `policy.promote_baseline` | 需要权限和非空 `reason`。 |
| `audit.query` | 需要 `audit.read` 权限。 |

审计结果含义：

| result | 含义 |
|---|---|
| `success` | 高风险操作或模型状态流转已执行。 |
| `denied` | 权限不足，操作被 RBAC 阻断。 |
| `rejected` | 权限通过但业务前置条件不满足，例如缺少原因、门禁未通过。 |
| `failed` | 下游执行异常或仿真交接失败。 |

---

## 4. 通用响应结构

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
    {"code": "NOT_FOUND", "message": "Task does not exist: task_999", "field": ""}
  ],
  "request_id": "req-demo-1"
}
```

HTTP 错误映射：

| API 错误码 | HTTP 状态码 |
|---|---:|
| `NOT_FOUND` | 404 |
| `FORBIDDEN` | 403 |
| `CONFLICT` / `STATE_CONFLICT` | 409 |
| `INVALID_REQUEST` | 422 |
| 其他错误 | 500 |

---

## 5. Endpoint 总览

| 能力域 | HTTP / WS | Facade 方法 | 所需权限 | 说明 |
|---|---|---|---|---|
| Health | `GET /api/v1/health` | transport only | 无 | 服务健康检查。 |
| Task | `POST /api/v1/tasks` | `submit_task` | `task.submit` | 提交中文自然语言任务并生成执行预览。 |
| Task | `POST /api/v1/tasks/{task_id}/confirm` | `confirm_task` | `task.confirm` | 确认执行预览。 |
| Task | `POST /api/v1/tasks/{task_id}/handoff` | `handoff_task` | `task.handoff` | 将已确认任务交给控制运行。 |
| Task | `POST /api/v1/tasks/{task_id}/cancel` | `cancel_task` | `task.cancel` | 取消尚未 handoff 的任务，要求 `reason`。 |
| Control | `GET /api/v1/control/{run_id}` | `get_control_status` | `control.read` | 查询控制运行状态。 |
| Control | `POST /api/v1/control/{run_id}/override` | `override_control` | 按 `command_type` 映射 | 急停、Safe-Stand、暂停、恢复或人工接管。 |
| Training | `POST /api/v1/training/plans` | `submit_training_plan` | `training.submit` | 创建训练计划并进入 queued。 |
| Policy | `POST /api/v1/policies` | `register_policy` | `policy.register` | 注册候选策略并写入审计。 |
| Policy | `POST /api/v1/policies/gate-report` | `attach_gate_report` | `policy.gate_report` | 附加门禁结论，要求 `reason`。 |
| Policy | `POST /api/v1/policies/{policy_id}/{policy_version}/release` | `release_policy` | `policy.release` | 发布已通过门禁的策略，要求 `reason`。 |
| Policy | `POST /api/v1/policies/{policy_id}/{policy_version}/baseline` | `promote_policy_baseline` | `policy.promote_baseline` | 提升策略为当前 baseline，要求 `reason`。 |
| Replay | `GET /api/v1/replay/{run_id}` | `query_replay` | `replay.read` | 查询回放索引。 |
| Audit | `GET /api/v1/audit` | `query_audit` | `audit.read` | 查询审计记录。 |
| Events | `GET /api/v1/events?run_id=...` | `query_events` | `events.read` | 查询当前事件。 |
| Events | `WS /api/v1/ws/events?run_id=...` | `query_events` | 内部 auditor 快照上下文 | WebSocket 事件快照。 |

---

## 6. Task API

### `POST /api/v1/tasks`

请求：

```json
{
  "source_text": "避开低摩擦区，先巡检A，再巡检B，最后回到平台待命",
  "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
  "require_confirmation": true
}
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

### `POST /api/v1/tasks/{task_id}/cancel`

请求：

```json
{"reason": "operator cancelled before handoff"}
```

成功取消会追加 `task.cancel` 审计记录和 `audit.record` 事件。缺少原因返回 `422 INVALID_REQUEST`。

---

## 7. Control API

### `POST /api/v1/control/{run_id}/override`

请求：

```json
{
  "command_type": "emergency_stop",
  "reason": "答辩急停演示"
}
```

`command_type` 映射：

| command_type | action | reason |
|---|---|---|
| `emergency_stop` | `control.emergency_stop` | 可空 |
| `safe_stand` | `control.safe_stand` | 可空 |
| `manual_control` | `control.manual_control` | 必填 |
| `pause` | `control.pause` | 可空 |
| `resume` | `control.resume` | 可空 |

成功后写入一条对应 action 的审计记录，并发布 `control.alert` 事件。

---

## 8. Training 与 Policy API

训练计划请求：

```json
{
  "training_id": "train-1",
  "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
  "algorithm": "ppo_placeholder",
  "max_iterations": 100,
  "num_envs": 1,
  "seed": 42
}
```

策略注册请求：

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

门禁报告请求：

```json
{
  "policy_ref": {"id": "flat_nav", "version": "1.0.0"},
  "decision": "passed",
  "reason": "meets baseline gate"
}
```

发布与基线切换均要求策略已满足状态前置条件，并要求非空 `reason`。门禁未通过发布或非 released 策略提升 baseline 时返回 `409 STATE_CONFLICT`，并写入 `result=rejected` 审计记录。

---

## 9. Replay / Audit / Events API

### `GET /api/v1/replay/{run_id}`

返回 `ReplayResponse`，包含 `segment_count`、`keyframe_count`、`manifest_uri` 和 `manifest_checksum` 等字段。

### `GET /api/v1/audit`

查询参数：

| 参数 | 说明 |
|---|---|
| `actor_id` | 按操作者过滤。 |
| `object_id` | 按对象 ID 过滤。 |
| `action` | 按动作过滤。 |

响应 `data`：

```json
{
  "count": 1,
  "audit_ids": ["audit_1"],
  "records": []
}
```

### `GET /api/v1/events?run_id=<run_id>`

统一返回 `ApiResponse` 封装：

```json
{
  "ok": true,
  "data": {
    "count": 1,
    "events": []
  },
  "request_id": "req-demo-1"
}
```