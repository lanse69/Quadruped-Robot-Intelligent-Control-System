# QRICS HTTP API / API Facade 契约

本文档描述 QRICS 应用接口族、请求/响应结构、HTTP 映射、RBAC 门控、事件查询和 WebSocket 快照接口。场景资源 API 与本机仿真后端选择 API 已纳入同一接口族，用于支撑场景模板版本化、基线发布、任务/训练 scene_ref 校验、MuJoCo / Webots 本机预览和审计追踪。当前仓库提供两层 API：

1. `python/qrics/api/app.py`：依赖标准库的 `QricsApiApp` 应用 Facade，承载任务、控制、训练、策略、回放、审计和事件流的业务边界。
2. `python/qrics/api/http_app.py`：可选 FastAPI / WebSocket 传输适配层，暴露 `/api/v1` HTTP 接口和 `/api/v1/ws/events` WebSocket 事件快照。

HTTP 层不得承载领域规则；它只负责请求上下文提取、JSON 转换、错误映射和事件输出。权限矩阵、高风险操作和枚举校验由 `qrics.api.security` 统一定义，状态流转和审计写入由 `QricsApiApp` 统一处理。

---

## 1. 设计边界

当前 API 的目标是在本机环境内让场景资源、任务执行、控制状态、训练作业、策略治理、回放索引、审计记录和事件快照可测试、可演示、可追溯。

约束：

- API 层不得接收或下发未经过安全语义建模的底层关节命令。
- API 层不暴露 MuJoCo、Isaac Lab、Webots 等后端内部对象。
- 进入仿真后端的动作必须是经过 Safety Shield 语义约束后的安全动作。
- 训练、策略治理、审计查询等接口默认不授予高权限；调用方必须显式声明角色。
- 高风险操作的成功、权限失败和业务拒绝路径必须写入追加式审计记录。
- 任务提交和训练计划提交必须引用已存在且未归档的 `scene_ref`；不得继续使用未登记或已归档场景。
- 基础 `import qrics.api` 应保持无 FastAPI 依赖；需要 HTTP 服务时显式导入 `qrics.api.http_app` 或使用 `scripts/run_api_service.py`。

---

## 2. 运行入口

安装 API 依赖：

```bash
python -m pip install -e ".[api,dev]"
```

启动 API 服务：

```bash
python scripts/run_api_service.py --host 127.0.0.1 --port 8000
```

启动带 Web Console 的本机演示服务：

```bash
python scripts/run_web_console.py --host 127.0.0.1 --port 8000
```

Web Console 入口为 `http://127.0.0.1:8000/console/`。

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
| `operator` | 场景读取；任务提交、确认、交接、取消；控制状态读取；急停、Safe-Stand、人工接管、暂停、恢复；回放和事件读取。 |
| `algorithm_engineer` | 场景读取；训练计划提交、训练启动、检查点记录、训练完成/失败/取消、标准化评测、评测报告导出、策略注册、门禁报告、策略审批、策略发布、基线切换；控制状态、回放、策略审批记录和事件读取。 |
| `test_engineer` | 场景创建、复制、发布基线、归档与读取；任务执行、控制安全操作、训练/评测只读、评测执行、评测报告导出、回放和事件读取。 |
| `auditor` | 场景读取、训练只读、评测只读、评测报告导出、策略审批记录读取、审计查询、事件查询和回放查询。 |
| `admin` | 当前所有应用层权限。 |

非提权规范化规则：HTTP / WebSocket 层收到缺失或未知角色时统一规范化为 `operator`，不会获得训练、策略发布或审计查询权限；角色已规范化但缺少权限时返回 `403 FORBIDDEN`，并追加审计记录，`result=denied`。

### 3.4 高风险操作门控

| action | 要求 |
|---|---|
| `scene.publish_baseline` | 需要权限和非空 `reason`。 |
| `scene.archive` | 需要权限和非空 `reason`。 |
| `task.cancel` | 需要权限和非空 `reason`。 |
| `control.emergency_stop` | 需要权限；不强制原因，避免阻塞急停路径。 |
| `control.safe_stand` | 需要权限；不强制原因。 |
| `control.manual_control` | 需要权限和非空 `reason`。 |
| `control.pause` | 需要权限；不强制原因。 |
| `control.resume` | 需要权限；不强制原因。 |
| `policy.gate_report` | 需要权限和非空 `reason`。 |
| `policy.approve` | 需要权限和非空 `reason`；批准前必须存在同策略的已通过评测报告。 |
| `policy.release` | 需要权限和非空 `reason`；策略必须已通过门禁且具有 approved 审批证据。 |
| `policy.promote_baseline` | 需要权限和非空 `reason`。 |
| `training.fail` | 需要权限和非空 `reason`。 |
| `training.cancel` | 需要权限和非空 `reason`。 |
| `evaluation.export` | 需要 `evaluation.export` 权限；建议提供 `reason` 以便审计。 |
| `audit.query` | 需要 `audit.read` 权限。 |

### 3.5 RBAC 策略单一事实源

API Facade 与 FastAPI 传输层共享 `python/qrics/api/security.py` 中的权限矩阵、高风险操作策略、override action 映射、角色规范化和 gate decision 校验。应用服务不得在 `app.py`、route 文件或 HTTP adapter 中复制 `_PERMISSION_GROUPS`、`HIGH_RISK_OPERATIONS` 或 override action mapping。

非法 `command_type`、非法 gate `decision`、非法 approval `decision`、非法 report export `format`、缺少高风险操作 reason 均返回 `INVALID_REQUEST`，HTTP 状态码为 422。

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
| Scene | `POST /api/v1/scenes` | `create_scene` | `scene.write` | 创建或更新场景草稿。 |
| Scene | `GET /api/v1/scenes` | `list_scenes` | `scene.read` | 查询场景列表，可按状态过滤。 |
| Scene | `GET /api/v1/scenes/{scene_id}/{scene_version}` | `get_scene` | `scene.read` | 查询指定场景版本。 |
| Scene | `POST /api/v1/scenes/{scene_id}/{scene_version}/copy` | `copy_scene` | `scene.write` | 复制场景为新版本。 |
| Scene | `POST /api/v1/scenes/{scene_id}/{scene_version}/baseline` | `publish_scene_baseline` | `scene.publish_baseline` | 发布场景基线，要求 `reason`。 |
| Scene | `POST /api/v1/scenes/{scene_id}/{scene_version}/archive` | `archive_scene` | `scene.archive` | 归档场景版本，要求 `reason`。 |
| Simulation | `GET /api/v1/sim/backends` | `list_simulation_backends` | `scene.read` | 查询本机可选 `minimal` / `mujoco` / `webots` 后端、runtime profiles 和默认运行参数。 |
| Simulation | `GET /api/v1/sim/core-runtime` | `probe_cpp_core_runtime` | `scene.read` | 探测已构建的 C++ 核心任务运行时，返回二进制路径、执行命令和 JSON 运行证据。 |
| Simulation | `GET /api/v1/sim/readiness` | `get_demo_readiness` | `scene.read` | 检查本机答辩演示所需的 API、MuJoCo、Webots、C++ runtime、Web Console 静态资源、桌面入口和状态目录。 |
| Simulation | `POST /api/v1/sim/preview` | `preview_simulation` | `scene.read` | 使用指定场景和后端执行短仿真预览，返回控制状态、后端/profile、机器人位置、障碍检测和安全事件摘要。 |
| Task | `POST /api/v1/tasks` | `submit_task` | `task.submit` | 提交中文自然语言任务并生成执行预览。 |
| Task | `POST /api/v1/tasks/run` | `run_task` | `task.submit` / `task.confirm` / `task.handoff` | 一键完成任务解析、确认和本机仿真交接；Web Console 的“运行任务”入口使用该接口。 |
| Task | `POST /api/v1/tasks/{task_id}/confirm` | `confirm_task` | `task.confirm` | 确认执行预览。 |
| Task | `POST /api/v1/tasks/{task_id}/handoff` | `handoff_task` | `task.handoff` | 将已确认任务交给控制运行；可在 body 中传入 `run_options` 选择本机仿真后端和运行档位。 |
| Task | `POST /api/v1/tasks/{task_id}/cancel` | `cancel_task` | `task.cancel` | 取消尚未 handoff 的任务，要求 `reason`。 |
| Control | `GET /api/v1/control/{run_id}` | `get_control_status` | `control.read` | 查询控制运行状态。 |
| Control | `POST /api/v1/control/{run_id}/override` | `override_control` | 按 `command_type` 映射 | 急停、Safe-Stand、暂停、恢复或人工接管。 |
| Training | `POST /api/v1/training/plans` | `submit_training_plan` | `training.submit` | 创建训练计划并进入 queued。 |
| Training | `GET /api/v1/training/jobs` | `list_training_jobs` | `training.read` | 查询训练任务列表。 |
| Training | `GET /api/v1/training/jobs/{job_id}` | `get_training_job` | `training.read` | 查询训练任务详情。 |
| Training | `POST /api/v1/training/jobs/{job_id}/start` | `start_training_job` | `training.start` | queued -> running。 |
| Training | `POST /api/v1/training/jobs/{job_id}/checkpoint` | `record_training_checkpoint` | `training.checkpoint` | 记录检查点 URI 和迭代位置。 |
| Training | `POST /api/v1/training/jobs/{job_id}/complete` | `complete_training_job` | `training.complete` | running -> succeeded，并注册候选策略。 |
| Training | `POST /api/v1/training/jobs/{job_id}/fail` | `fail_training_job` | `training.fail` | running/queued -> failed，要求 `reason`。 |
| Training | `POST /api/v1/training/jobs/{job_id}/cancel` | `cancel_training_job` | `training.cancel` | running/queued -> cancelled，要求 `reason`。 |
| Evaluation | `POST /api/v1/evaluations` | `run_standard_evaluation` | `evaluation.run` | 执行标准化评测，生成门禁结论并更新策略 gate 状态。 |
| Evaluation | `GET /api/v1/evaluations` | `list_evaluation_reports` | `evaluation.read` | 查询评测报告列表。 |
| Evaluation | `GET /api/v1/evaluations/{evaluation_id}` | `get_evaluation_report` | `evaluation.read` | 查询评测报告详情。 |
| Evaluation | `POST /api/v1/evaluations/{evaluation_id}/exports` | `export_evaluation_report` | `evaluation.export` | 导出评测报告为 JSON 或 Markdown 工件。 |
| Evaluation | `GET /api/v1/evaluations/{evaluation_id}/exports` | `list_evaluation_report_exports` | `evaluation.read` | 查询某次评测的导出记录。 |
| Evaluation | `GET /api/v1/evaluation-exports/{export_id}` | `get_evaluation_report_export` | `evaluation.read` | 查询指定导出记录和 URI / checksum。 |
| Policy | `POST /api/v1/policies` | `register_policy` | `policy.register` | 注册候选策略并写入审计。 |
| Policy | `POST /api/v1/policies/gate-report` | `attach_gate_report` | `policy.gate_report` | 附加门禁结论，要求 `reason`。 |
| Policy | `POST /api/v1/policies/{policy_id}/{policy_version}/approval` | `approve_policy` | `policy.approve` | 对通过门禁的评测报告进行批准或拒绝，要求 `reason`。 |
| Policy | `GET /api/v1/policies/{policy_id}/{policy_version}/approvals` | `list_policy_approvals` | `policy.approval.read` | 查询指定策略审批记录。 |
| Policy | `POST /api/v1/policies/{policy_id}/{policy_version}/release` | `release_policy` | `policy.release` | 发布已通过门禁且已批准的策略，要求 `reason`。 |
| Policy | `POST /api/v1/policies/{policy_id}/{policy_version}/baseline` | `promote_policy_baseline` | `policy.promote_baseline` | 提升策略为当前 baseline，要求 `reason`。 |
| Replay | `GET /api/v1/replay/{run_id}` | `query_replay` | `replay.read` | 查询回放索引。 |
| Audit | `GET /api/v1/audit` | `query_audit` | `audit.read` | 查询审计记录。 |
| Events | `GET /api/v1/events?run_id=...` | `query_events` | `events.read` | 查询当前事件。 |
| Events | `WS /api/v1/ws/events?run_id=...` | `query_events` | `events.read` | WebSocket 事件快照；上下文来自连接 header 或查询参数，默认 `operator`。 |

---


## 6. Scene API

### `POST /api/v1/scenes`

请求：

```json
{
  "scene_id": "mixed_terrain_demo",
  "version": "0.1.0",
  "terrain_pack": "mixed",
  "assets": [
    {"asset_id": "cp_a", "asset_type": "checkpoint", "uri": "checkpoint://A"},
    {"asset_id": "low_mu", "asset_type": "forbidden_zone", "uri": "zone://low_friction"}
  ],
  "sensor_profile": {
    "camera_enabled": true,
    "depth_camera_enabled": true,
    "lidar_enabled": true,
    "imu_enabled": true,
    "foot_contact_enabled": true,
    "sample_rate_hz": 100,
    "noise_std": 0.01,
    "observation_sources": ["imu", "contact", "terrain"]
  },
  "randomization_profile": {
    "enabled": true,
    "friction_range": [0.4, 1.2],
    "mass_range": [0.9, 1.1],
    "sensor_noise_std": 0.02,
    "seed": 42
  },
  "metadata": {"owner": "simulation-test"}
}
```

响应 `data` 返回 `SceneProfilePayload`，关键字段：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `scene_id` | string | 场景 ID。 |
| `version` | string | 场景版本。 |
| `state` | string | `draft`、`published`、`archived`。 |
| `terrain_pack` | string | 目前 API 层允许 `flat`、`slope`、`gravel`、`stairs`、`low_friction`、`mixed`。 |
| `assets` | array | 地形、障碍、检查点、禁行区等资产引用。 |
| `sensor_profile` | object | 相机、深度相机、LiDAR、IMU、足端接触、采样率、噪声和观测来源。 |
| `randomization_profile` | object | 摩擦、质量、传感器噪声、种子等域随机化配置。 |
| `checksum` | string | 基于场景核心内容生成的确定性 SHA-256 摘要。 |
| `is_current_baseline` | boolean | 是否为该 `scene_id` 当前基线。 |

### `POST /api/v1/scenes/{scene_id}/{scene_version}/copy`

请求：

```json
{
  "new_version": "0.2.0",
  "reason": "新增碎石地形回归场景"
}
```

复制后新版本回到 `draft`，不会继承 `is_current_baseline=true`。若目标版本已存在，返回 `409 CONFLICT`。

### `POST /api/v1/scenes/{scene_id}/{scene_version}/baseline`

请求：

```json
{"reason": "场景资产校验通过，作为训练评估基线"}
```

发布基线前执行场景校验：`terrain_pack` 必须合法；资产 ID 不能为空且不能重复；资产 URI 不能为空，且不能用 `missing:` 表示缺失依赖；传感器采样率必须在 `1..1000`；噪声标准差不能为负；摩擦和质量随机化区间必须为正且上界不小于下界。成功后写入 `scene.publish_baseline` 审计记录和 `scene.lifecycle` 事件。

### `POST /api/v1/scenes/{scene_id}/{scene_version}/archive`

请求：

```json
{"reason": "被更高保真版本替换"}
```

归档后该场景版本不可再被新任务或训练计划引用。历史任务、训练和回放中的引用仍保留，不能被普通写操作覆盖。

### `GET /api/v1/scenes`

查询参数：

| 参数 | 说明 |
|---|---|
| `state` | 可选，按 `draft`、`published` 或 `archived` 过滤。 |
| `include_archived` | 可选，默认 `false`。 |

## 7. Simulation Backend API

### `GET /api/v1/sim/backends`

返回本机演示控制台可用的仿真后端与运行档位。该接口只暴露 QRICS 标准化后端标识，不泄露 MuJoCo、Webots 或其他运行时内部对象。

响应 `data` 关键字段：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `backends` | array[string] | 当前允许的后端：`minimal`、`mujoco`、`webots`。 |
| `runtime_profiles` | array[string] | 当前允许的运行档位：`headless_fast`、`balanced_visual`、`webots_fast`、`rich_demo`。 |
| `defaults` | object | 默认后端、profile、控制步数、前进速度、yaw rate 和障碍重规划距离。 |
| `recommended` | object | 本机答辩演示建议组合，例如 MuJoCo 物理预览和 Webots 可视化预览。 |

### `GET /api/v1/sim/core-runtime`

探测 C++ 核心任务运行时 `qrics_core_runtime` 是否已构建并可执行。该接口会运行一个短任务 smoke case，验证 C++ `TaskExecutor -> PolicyRuntime -> SafetyShield -> SimulationAdapter` 链路并返回 JSON 摘要。未构建二进制时返回 `available=false`，不阻断 Web Console 的 MuJoCo/Webots 主演示链路。

响应 `data` 关键字段：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `available` | boolean | C++ runtime 是否可执行且返回合法 JSON。 |
| `binary_path` | string | 检测到的 `qrics_core_runtime` 路径。 |
| `command` | array[string] | 本次自检执行的命令。 |
| `summary` | object | C++ runtime 输出摘要，包含 `run_id`、`state`、`executed_step_count`、`base_position`、`nodes`、`safety_events` 等字段。 |
| `error` | string | 不可用或执行失败时的原因。 |

构建命令：

```bash
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug
```

### `GET /api/v1/sim/readiness`

检查本机答辩演示链路的就绪状态。该接口不启动 MuJoCo、Webots、Uvicorn 或 C++ 运行时；它只执行轻量探测并返回阻断项、降级项和修复命令，供 Web Console 顶部“演示就绪检查”面板与命令行脚本复用。

响应 `data` 关键字段：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `status` | string | 总体状态：`ready`、`degraded` 或 `blocked`。必需项阻断时为 `blocked`，仅可选项缺失时为 `degraded`。 |
| `summary` | string | ready / degraded / blocked 数量摘要。 |
| `commands` | array[string] | 去重后的本机修复命令。 |
| `items` | array[object] | 每个检查项的 `item_id`、`name`、`status`、`severity`、`detail`、`command` 和 `path`。 |

命令行等价检查：

```bash
python scripts/check_demo_readiness.py --format markdown
python scripts/check_demo_readiness.py --format json
```

### `POST /api/v1/sim/preview`

使用已保存场景执行短仿真预览。该接口用于 Web Console 的“预览/打开仿真”按钮；若选择 Webots 且本机存在 `webots` 可执行程序，Webots 适配层会按当前运行档位尝试启动可视化仿真。

请求：

```json
{
  "scene_ref": {"id": "demo_scene", "version": "0.1.0"},
  "run_options": {
    "backend": "mujoco",
    "runtime_profile": "balanced_visual",
    "step_count": 60,
    "forward_velocity_mps": 0.25,
    "yaw_rate_radps": 0.05,
    "obstacle_replan_distance_m": 0.25,
    "auto_extend_task_steps": false
  }
}
```

响应 `data` 复用 `ControlStatusResponse` 结构。预览成功时 `run_id` 形如 `preview_<scene_id>_<scene_version>`，`state=succeeded`；预览失败时 `state=failed`，并返回 `latest_action=simulation_failed` 和可解释错误消息，同时写入 `control.status` 事件。

### `SimulationRunOptionsPayload`

| 字段 | 类型 | 默认值 | 说明 |
|---|---:|---:|---|
| `backend` | string | `minimal` | `minimal`、`mujoco` 或 `webots`。 |
| `runtime_profile` | string | `headless_fast` | `headless_fast`、`balanced_visual`、`webots_fast` 或 `rich_demo`。 |
| `step_count` | integer | `20` | 本次预览或 handoff 执行控制步数。 |
| `forward_velocity_mps` | number | `0.25` | 演示用前进速度建议值，仍需经过控制链路和安全语义约束。 |
| `yaw_rate_radps` | number | `0.05` | 演示用 yaw rate 建议值。 |
| `obstacle_replan_distance_m` | number | `0.25` | 障碍物距离低于该阈值时，本机仿真摘要会标记避障/重规划风险。 |
| `auto_extend_task_steps` | boolean | `false` | 仅任务 handoff 有效；为 `true` 时按任务路径长度、控制周期和驻留时间自动扩展 bounded simulation 步数，上限为 1200，用于确保本机演示能跑完整个 A/B/平台路径。 |

`POST /api/v1/tasks/{task_id}/handoff` 保持向后兼容：不传 body 时沿用应用默认后端和 profile；传入以下 body 时使用指定后端运行已确认任务。

```json
{
  "run_options": {
    "backend": "webots",
    "runtime_profile": "webots_fast",
    "step_count": 80
  }
}
```

---

## 7. Task API

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
| `waypoints` | array[string] | 解析出的路径点 ID；保留为兼容字段。 |
| `waypoint_details` | array[object] | 路径点详情，包含 `waypoint_id`、`name`、`terrain_hint`、`dwell_time_s`。 |
| `selected_policy_reason` | string | 策略选择解释。 |
| `risk_summary` | string | 执行前风险说明。 |
| `operator_action_required` | boolean | 是否需要操作者确认。 |
| `scene_id` | string | 已校验的任务场景 ID。 |
| `scene_version` | string | 已校验的任务场景版本。 |
| `parser_version` | string | 任务解析器版本，例如 `rule-based-zh-api-0.2.0`。 |
| `parse_confidence` | number | 任务解析置信度。 |
| `constraints` | array[string] | 已识别禁行/避让区域 ID。 |
| `fallback_action` | string | 失败或风险触发时的建议回退动作。 |
| `explanation` | array[string] | 任务解析、约束和安全边界说明。 |
| `task_script` | object | TaskScript 草案；仅包含目标、路径点、约束、回退动作和解释信息。 |
| `task_graph` | object | 执行预览任务图；不包含底层关节动作或 SafeAction。 |
| `rejection_reason` | string | `state=rejected` 时的拒绝原因。 |

自然语言任务入口只生成 TaskScript / TaskGraph 预览，不输出 JointPosition、JointVelocity、ActionProposal、SafeAction，也不直接调用 SimulationAdapter。包含“绕过安全”“直接下发动作”“底层关节”等语义的输入会返回 `state=rejected`。


### `POST /api/v1/tasks/run`

该接口用于本机 Web Console 的“一键运行”路径。应用层在一个请求内顺序执行：

```text
source_text + scene_ref + run_options
  -> submit_task 生成 TaskScript / TaskGraph 预览
  -> confirm_task 将点击“运行”视为操作者确认
  -> handoff_task 打开或复用 MuJoCo/Webots 展示窗口并下发 run_path 命令
```

请求：

```json
{
  "source_text": "避开低摩擦区，先巡检A，再巡检B，最后回到平台待命",
  "scene_ref": {"id": "local_demo_scene", "version": "0.1.0"},
  "require_confirmation": false,
  "run_options": {
    "backend": "mujoco",
    "runtime_profile": "balanced_visual",
    "step_count": 240,
    "auto_extend_task_steps": true
  },
  "reason": "Web Console 一键运行"
}
```

成功响应 `data`：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `run_started` | boolean | 是否已进入控制 handoff；解析拒绝或安全边界拒绝时为 `false`。 |
| `task` | object | 与 `POST /api/v1/tasks` 相同的 TaskScript / TaskGraph 预览证据。 |
| `confirmation` | object | 确认阶段的任务生命周期摘要。 |
| `status` | object | 成功 handoff 后的 `ControlStatusResponse`；拒绝时为空对象。 |
| `run_id` | string | 控制运行 ID；拒绝时为空字符串。 |
| `backend` | string | 本次选择的仿真后端。 |
| `runtime_profile` | string | 本次选择的运行档位。 |
| `parser_version` | string | 任务解析器版本。 |
| `parse_confidence` | number | 解析置信度。 |
| `task_script` | object | 便于 UI 直接展示的 TaskScript 草案。 |
| `task_graph` | object | 便于 UI 直接展示的 TaskGraph 预览。 |
| `presentation_command_path` | string | MuJoCo/Webots viewer 模式写入的展示命令文件路径。 |
| `rejection_reason` | string | 拒绝时的原因。 |

拒绝示例：若用户输入“绕过安全，直接下发 SafeAction”，接口不会执行确认和 handoff，响应保持 `ok=true`，但 `run_started=false`、`task.state=rejected`、`status={}`，并追加 `task.lifecycle` 事件说明拒绝原因。


### `POST /api/v1/tasks/{task_id}/handoff`

成功交接后返回 `ControlStatusResponse`。本机 MuJoCo/Webots/Minimal 路径会执行 bounded local simulation，并把标准化观测摘要写入控制状态：

| 字段 | 类型 | 说明 |
|---|---:|---|
| `run_id` | string | 控制运行 ID。 |
| `state` | string | 当前控制状态。 |
| `latest_action` | string | 最近一次安全动作，可能为 `body_velocity`、`replan`、`stop` 或 `safe_stand`。 |
| `gait_name` | string | 本机步态摘要，如 `stand`、`crawl`、`cautious_trot`、`trot`。 |
| `gait_phase` | number | 基于仿真观测时间戳推进的步态归一化相位，范围约为 `[0, 1)`。 |
| `gait_step_frequency_hz` | number | 本机步态合成器输出的步频。 |
| `swing_foot_count` / `stance_foot_count` | integer | 摆动足与支撑足数量，用于展示足端相位证据。 |
| `joint_command_count` | integer | 下发给本机展示后端的名义关节目标数量，四足三关节模型通常为 `12`。 |
| `active_target_id` | string | 当前正在跟踪或已完成保持的任务目标 ID。 |
| `reached_target_ids` | array[string] | 本机闭环已判定到达的任务目标序列。 |
| `target_count` / `reached_target_count` | integer | 任务目标总数与已到达数量。 |
| `route_completed` | boolean | 是否已按任务路径到达全部目标并进入末端保持。 |
| `route_progress_ratio` | number | 路径到达进度，按已到达目标数 / 目标总数计算。 |
| `target_distance_m` | number | 当前目标剩余平面距离；完成后为末端目标保持误差。 |
| `requested_step_count` / `effective_step_count` | integer | 用户请求控制步数与实际执行控制步数。启用 `auto_extend_task_steps` 时后者可能更大。 |
| `estimated_required_step_count` | integer | 按路径长度、速度、控制周期和驻留时间估计出的最低演示步数。 |
| `backend` | string | 本次 handoff 使用的仿真后端。 |
| `runtime_profile` | string | 本次 handoff 使用的运行档位。 |
| `control_step_count` | integer | 已执行控制步数。 |
| `sim_time_ns` | integer | 最新仿真时间戳。 |
| `base_position` | array[number] | 最新 base 位置 `[x, y, z]`。 |
| `observation_quality` | string | 观测来源质量，Minimal 通常为 `estimated`。 |
| `terrain_class` | string | 最新地形类别。 |
| `obstacle_detected` | boolean | 是否检测到场景障碍。 |
| `nearest_obstacle_distance_m` | number | 最近障碍表面距离。 |
| `safety_event_count` | integer | 本次 handoff 中的安全事件数量。 |

### `POST /api/v1/tasks/{task_id}/cancel`

请求：

```json
{"reason": "operator cancelled before handoff"}
```

成功取消会追加 `task.cancel` 审计记录和 `audit.record` 事件。缺少原因返回 `422 INVALID_REQUEST`。

---

## 8. Control API

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
| `pause` | `control.pause` | 必填 |
| `resume` | `control.resume` | 必填 |

成功后写入一条对应 action 的审计记录，并发布 `control.alert` 事件。

---

## 9. Training、Evaluation 与 Policy API

训练计划请求。`scene_ref` 必须引用已存在且未归档的场景版本。应用层会生成确定性 `config_hash`，将算法、场景、奖励版本、域随机化模板、资源配额和检查点间隔固化为可追溯配置摘要：

```json
{
  "training_id": "train-1",
  "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
  "algorithm": "ppo_placeholder",
  "max_iterations": 100,
  "num_envs": 1,
  "seed": 42,
  "reward_config_version": "reward.default.v1",
  "randomization_profile_id": "no_randomization",
  "checkpoint_interval": 10,
  "resource_quota": {
    "gpu_count": 0,
    "cpu_threads": 2,
    "memory_gb": 4.0,
    "max_runtime_s": 3600
  }
}
```

训练任务状态机：

```text
queued -> running -> succeeded
queued/running -> failed
queued/running -> cancelled
```

检查点请求只能作用于 `running` 任务，且 `iteration` 必须递增、不得超过 `max_iterations`：

```json
{
  "iteration": 10,
  "checkpoint_uri": "file://ckpt/train-1/10.pt",
  "reason": "periodic checkpoint"
}
```

完成训练请求会将训练任务置为 `succeeded`，同时注册一个候选策略并保留指标摘要：

```json
{
  "policy_ref": {"id": "flat_nav", "version": "1.0.0"},
  "artifact_uri": "artifact://policies/flat_nav/1.0.0/model.pt",
  "checksum": "sha256:demo",
  "final_iteration": 100,
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

标准化评测请求会生成 `EvaluationReportResponse`，计算候选策略与当前 baseline 的指标差异，并按当前门禁阈值更新策略状态为 `gate_passed` 或 `gate_failed`。当前轻量门禁阈值为：`success_rate >= 0.80`、`collision_rate <= 0.05`、`tracking_error_m <= 0.30` 且 `hard_constraint_violation_count == 0`。

```json
{
  "evaluation_id": "eval-flat-nav-1",
  "policy_ref": {"id": "flat_nav", "version": "1.0.0"},
  "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
  "suite_id": "standard_v1",
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

策略注册请求仍可用于手工导入候选策略：

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

策略批准请求：

```json
{
  "evaluation_id": "eval-flat-nav-1",
  "decision": "approved",
  "reason": "标准化评测通过，批准进入发布候选"
}
```

`decision` 取值为 `approved` 或 `rejected`。批准时，目标评测报告必须属于同一策略，且评测结论必须为 `passed`。批准通过后策略阶段进入 `approved`；拒绝时保留策略但记录拒绝原因。

评测报告导出请求：

```json
{
  "format": "markdown",
  "reason": "形成评审证据"
}
```

响应包含 `export_id`、`evaluation_id`、`report_format`、`uri`、`checksum`、`size_bytes`、`generated_by`、`request_id`、`timestamp_ns` 和 `summary`。配置了 `FileObjectStore` 时，导出内容写入本地不可变对象目录；否则 SQLite 仓储以内联文本和 `sqlite://evaluation_report/<export_id>` URI 保留证据。

发布与基线切换均要求策略已满足状态前置条件，并要求非空 `reason`。发布前必须同时存在通过的门禁报告与 `approved` 审批记录；缺少任一证据时返回 `409 STATE_CONFLICT`，并写入 `result=rejected` 审计记录。非 released 策略提升 baseline 同样返回 `409 STATE_CONFLICT`。

---

## 10. Replay / Audit / Events API

### `GET /api/v1/replay/{run_id}`

返回 `ReplayResponse`，包含 `segment_count`、`keyframe_count`、`manifest_uri`、`manifest_checksum`、`keyframes` 和 `safety_events` 等字段。`safety_events` 用于呈现 handoff 期间由标准化观测触发的 `CollisionRisk`、重规划等安全证据。

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

## 本机仿真后端说明

API Facade 的本机 `LocalSimulationRunner` 支持 `minimal`、`mujoco`、`webots` 三类 backend。HTTP / WebSocket 层不暴露 MuJoCo、Webots 或 Isaac Lab 内部对象，只传递任务、控制状态、回放、审计和运行证据字段。步态遥测字段见 `docs/runbooks/api_gait_telemetry.md`，Webots 本机演示后端的运行方式见 `docs/runbooks/webots_local_backend.md`。

## 11. C++ Core Runtime Evidence

### `GET /api/v1/sim/core-runtime`

执行一次有步数上限的 C++ runtime smoke run。该接口只用于探测二进制和核心链路可用性，不会打开 MuJoCo/Webots viewer。

响应 `data`：

```json
{
  "available": true,
  "binary_path": "build/dev-gcc-debug/qrics_core_runtime",
  "command": ["..."],
  "summary": {
    "run_id": "py_core_probe",
    "state": "running",
    "executed_step_count": 8,
    "scene_obstacle_count": 1,
    "scene_forbidden_zone_count": 1
  },
  "error": ""
}
```

### 任务 handoff / 一键运行中的 C++ 证据

`POST /api/v1/tasks/run` 和 `POST /api/v1/tasks/{task_id}/handoff` 的 `status` 响应新增：

```json
{
  "core_runtime_available": true,
  "core_runtime_summary": {
    "available": true,
    "binary_path": "build/dev-gcc-debug/qrics_core_runtime",
    "command": ["...", "--clear-default-assets", "--obstacle", "box_1:box:..."],
    "summary": {
      "scene_id": "local_demo_scene",
      "scene_version": "0.1.0",
      "task_target_count": 3,
      "scene_obstacle_count": 2,
      "scene_forbidden_zone_count": 1,
      "state": "running",
      "replay_manifest_path": "runtime/qrics-console/core_runtime_evidence/run_task_1_core_replay_manifest.json",
      "telemetry_path": "runtime/qrics-console/core_runtime_evidence/run_task_1_core_telemetry.jsonl",
      "audit_path": "runtime/qrics-console/core_runtime_evidence/run_task_1_core_audit.jsonl",
      "evidence_bundle_path": "runtime/qrics-console/core_runtime_evidence/run_task_1_core_evidence_bundle.json"
    },
    "error": ""
  },
  "core_runtime_error": ""
}
```

若 C++ 二进制未构建，`core_runtime_available=false`，`core_runtime_error` 返回构建提示；应用层仍继续执行本机展示和回放审计链路。若应用启动时配置了 `core_runtime_evidence_dir`，`summary` 中会返回 C++ replay、telemetry、audit 和 evidence bundle 文件路径，用于证明核心运行链路已独立落盘。