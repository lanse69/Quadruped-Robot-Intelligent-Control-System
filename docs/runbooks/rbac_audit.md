# QRICS RBAC 与审计门控运行手册

## 1. 请求上下文

HTTP 请求通过 header 提供应用层身份上下文：

```text
x-request-id: req-demo-001
x-actor-id: operator-1
x-actor-role: operator
```

缺省角色为 `operator`。除任务执行、控制操作、回放和事件读取外，训练、策略治理和审计查询都需要显式传入对应角色。

当前 header 只作为本机演示和应用层权限上下文，不是生产级身份认证。接入真实认证系统后，`RequestContext` 必须由认证中间件生成，不允许客户端直接声明任意角色。

## 2. 常用角色

| 场景 | 推荐角色 |
|---|---|
| 提交、确认、交接任务 | `operator` |
| 急停、Safe-Stand、暂停、恢复、人工接管 | `operator` 或 `test_engineer` |
| 提交训练计划 | `algorithm_engineer` |
| 注册候选策略和附加门禁报告 | `algorithm_engineer` |
| 发布策略和切换基线 | `algorithm_engineer` 或 `admin` |
| 查询审计日志 | `auditor` 或 `admin` |
| 查询事件和回放 | `operator`、`test_engineer`、`algorithm_engineer`、`auditor` 或 `admin` |

## 3. 高风险操作原因

以下操作必须提供非空 `reason`：

```text
task.cancel
control.manual_control
policy.gate_report
policy.release
policy.promote_baseline
```

以下操作不强制原因，但仍写入审计：

```text
control.emergency_stop
control.safe_stand
control.pause
control.resume
```

`control.emergency_stop` 不强制原因，是为了确保急停路径始终可达，不被表单字段阻塞。

## 4. 审计结果说明

| result | 含义 |
|---|---|
| `success` | 高风险操作或模型状态流转已执行。 |
| `denied` | 权限不足，操作被 RBAC 阻断。 |
| `rejected` | 权限通过但业务前置条件不满足，例如缺少原因、门禁未通过或状态不允许。 |
| `failed` | 下游执行异常或仿真交接失败。 |

## 5. 验证示例

训练接口不应默认获得高权限：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/training/plans \
  -H 'content-type: application/json' \
  -d '{"training_id":"train-1","scene_ref":{"id":"minimal_scene","version":"0.1.0"}}'
```

预期返回 `403 FORBIDDEN`，并写入一条 `training.submit` / `denied` 审计记录。

使用算法工程师角色提交训练：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/training/plans \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-train-1' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{"training_id":"train-1","scene_ref":{"id":"minimal_scene","version":"0.1.0"}}'
```

注册候选策略：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/policies \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-policy-1' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{
    "policy_ref":{"id":"flat_nav","version":"1.0.0"},
    "artifact_uri":"artifact://policies/flat_nav/1.0.0/model.pt",
    "metrics":{
      "success_rate":0.95,
      "collision_rate":0.01,
      "tracking_error_m":0.08,
      "recovery_rate":0.90,
      "energy_proxy":30.0
    }
  }'
```

发布策略必须提供原因：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/policies/flat_nav/1.0.0/release \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-release-1' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{"reason":"通过标准化门禁，发布为候选可执行策略"}'
```

查询审计日志：

```bash
curl -s http://127.0.0.1:8000/api/v1/audit \
  -H 'x-request-id: req-audit-1' \
  -H 'x-actor-id: auditor-1' \
  -H 'x-actor-role: auditor'
```

查询事件：

```bash
curl -s 'http://127.0.0.1:8000/api/v1/events?run_id=run_task_1' \
  -H 'x-request-id: req-events-1' \
  -H 'x-actor-id: operator-1' \
  -H 'x-actor-role: operator'
```

## 6. 故障排查

### 6.1 返回 `403 FORBIDDEN`

检查：

1. 是否传入 `x-actor-role`。
2. 该角色是否具备目标 action 对应权限。
3. 审计日志中是否存在同一 `request_id` 的 `result=denied` 记录。

### 6.2 返回 `422 INVALID_REQUEST` 且 field 为 `reason`

说明权限已通过，但高风险操作缺少原因。补充非空 `reason` 后重试。

### 6.3 返回 `409 STATE_CONFLICT`

说明业务状态不满足要求，例如：

- 策略未通过门禁就尝试发布。
- 非 released 策略尝试切换为 baseline。
- 已 handoff 的任务尝试取消。

该类拒绝应伴随 `result=rejected` 审计记录。

## 7. 运行约束

- 不得在日志、错误响应或回放文件中写入访问 token、对象存储密钥或模型签名私钥。
- 审计记录只追加，不应被普通业务操作覆盖。
- 高风险操作的失败、拒绝和成功路径都必须能通过 `request_id`、`actor_id`、`action` 或 `object_id` 检索。
- 当前 RBAC 是应用层语义，不替代生产级身份认证、真实会话、JWT/OIDC、密钥管理、对象级授权和审批工作流。