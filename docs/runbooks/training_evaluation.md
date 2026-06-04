# QRICS 训练评测运行手册

## 1. 目的

本手册说明当前本机 API 层如何提交训练计划、推进训练状态、记录检查点、完成训练并注册候选策略、运行标准化评测、查询/导出评测报告、记录策略审批以及发布策略。当前实现是运行证据闭环和接口契约，不代表已经接入真实 Isaac Lab / GPU 强化学习后端。

## 2. 角色与权限

- `algorithm_engineer`：可提交、启动、检查点、完成、失败、取消训练任务；可运行评测；可导出评测报告；可注册、门禁、审批、发布和基线切换策略。
- `test_engineer`：可读取训练任务并运行/读取评测，可导出评测报告，用于回归验证。
- `auditor`：可读取训练任务、评测报告、评测导出记录、策略审批记录、事件和审计。
- `operator`：无训练、评测和策略发布权限。

## 3. 启动 API 服务

```bash
python -m pip install -e ".[api,dev]"
python scripts/run_api_service.py --state-dir runtime/qrics-api
```

请求头示例：

```bash
-H 'x-request-id: req-train-demo' \
-H 'x-actor-id: algo-1' \
-H 'x-actor-role: algorithm_engineer'
```

## 4. 提交训练计划

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/training/plans \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-train-plan' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{
    "training_id": "demo-001",
    "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
    "algorithm": "ppo_local_smoke",
    "max_iterations": 40,
    "num_envs": 4,
    "seed": 7,
    "reward_config_version": "reward.walk.v2",
    "randomization_profile_id": "local_domain_randomization",
    "checkpoint_interval": 5,
    "resource_quota": {
      "gpu_count": 0,
      "cpu_threads": 4,
      "memory_gb": 6.0,
      "max_runtime_s": 900
    }
  }'
```

响应中的 `config_hash` 是训练配置摘要，用于后续审计、复现和报告串联。

## 5. 启动训练并记录检查点

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/training/jobs/job_demo-001/start \
  -H 'x-request-id: req-train-start' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer'

curl -s -X POST http://127.0.0.1:8000/api/v1/training/jobs/job_demo-001/checkpoint \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-train-ckpt' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{"iteration": 10, "checkpoint_uri": "file://ckpt/demo-001/10.pt"}'
```

检查点要求：训练任务必须处于 `running`，`iteration` 必须递增且不超过 `max_iterations`，`checkpoint_uri` 必须非空。

## 6. 完成训练并注册候选策略

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/training/jobs/job_demo-001/complete \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-train-complete' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{
    "policy_ref": {"id": "demo_nav", "version": "1.0.0"},
    "artifact_uri": "artifact://policies/demo_nav/1.0.0/model.pt",
    "checksum": "sha256:demo-nav",
    "final_iteration": 40,
    "metrics": {
      "success_rate": 0.91,
      "collision_rate": 0.01,
      "tracking_error_m": 0.12,
      "recovery_rate": 0.88,
      "energy_proxy": 24.0,
      "hard_constraint_violation_count": 0
    },
    "reason": "候选策略训练完成"
  }'
```

训练完成后，训练任务状态变为 `succeeded`，候选策略进入 `candidate`。

## 7. 运行标准化评测

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/evaluations \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-eval' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{
    "evaluation_id": "eval-demo-nav-1",
    "policy_ref": {"id": "demo_nav", "version": "1.0.0"},
    "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
    "suite_id": "standard_v1",
    "metrics": {
      "success_rate": 0.91,
      "collision_rate": 0.01,
      "tracking_error_m": 0.12,
      "recovery_rate": 0.88,
      "energy_proxy": 24.0,
      "hard_constraint_violation_count": 0
    }
  }'
```

当前门禁阈值：

- `success_rate >= 0.80`
- `collision_rate <= 0.05`
- `tracking_error_m <= 0.30`
- `hard_constraint_violation_count == 0`

通过后策略进入 `gate_passed`；否则进入 `gate_failed`。评测报告会保存 baseline 对比差异。

## 8. 批准策略

通过门禁后，发布前必须补充审批记录。批准请求会校验评测报告是否属于目标策略，并且 `approved` 只能用于 `passed` 评测报告。

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/policies/demo_nav/1.0.0/approval \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-approval' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{
    "evaluation_id": "eval-demo-nav-1",
    "decision": "approved",
    "reason": "标准化评测通过，批准进入发布候选"
  }'
```

审批通过后策略进入 `approved`。审批缺少 `reason` 会返回 `422 INVALID_REQUEST`。评测报告与策略不匹配或失败评测被批准会返回 `409 STATE_CONFLICT`，并写入 `result=rejected` 审计记录。

## 9. 导出评测报告

评测报告可以导出为 `json` 或 `markdown`，用于评审附件、验收证据和后续归档。

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/evaluations/eval-demo-nav-1/exports \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-export' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{"format": "markdown", "reason": "形成评审证据"}'
```

响应会返回 `export_id`、`uri`、`checksum`、`size_bytes` 和 `summary`。使用 `--state-dir` 启动服务时，导出内容会写入本地不可变对象存储；未配置对象存储时，SQLite 仓储以内联文本和 `sqlite://evaluation_report/<export_id>` URI 记录证据。

## 10. 发布策略

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/policies/demo_nav/1.0.0/release \
  -H 'content-type: application/json' \
  -H 'x-request-id: req-release' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{"reason": "标准化评测和审批均通过，发布为可执行候选"}'
```

`reason` 为空会返回 `422 INVALID_REQUEST`。未通过门禁或没有 `approved` 审批证据时，发布会返回 `409 STATE_CONFLICT` 并写入 `result=rejected` 审计记录。

## 11. 验证命令

```bash
python -m pytest tests/python/test_training_evaluation_runtime.py
python -m pytest tests/python
cmake --build --preset dev-gcc-debug
ctest --preset dev-gcc-debug --output-on-failure
```

如果本地安装了格式和类型工具，还应执行：

```bash
python -m ruff check python tests/python
python -m black --check python tests/python
python -m mypy python tests/python
```