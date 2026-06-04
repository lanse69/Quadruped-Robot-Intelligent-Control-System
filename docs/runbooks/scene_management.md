# 场景资源管理运行手册

本运行手册说明如何使用本地 QRICS API 的场景管理边界。适用范围包括开发、演示和回归测试。

## 1. 启动 API 服务

安装 API 依赖，并以 SQLite 持久化方式启动服务：

```bash
python -m pip install -e ".[api,dev]"
python scripts/run_api_service.py --state-dir runtime/qrics-api --host 127.0.0.1 --port 8000
```

当仓储为空时，应用会自动写入默认已发布基线 `minimal_scene:0.1.0`。该基线可用于冒烟测试；也可以通过 Scene API 创建更完整的场景配置档案。

## 2. 创建场景草稿

创建场景需要 `test_engineer` 或 `admin` 权限。

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/scenes \
  -H 'content-type: application/json' \
  -H 'x-actor-id: sim-test-1' \
  -H 'x-actor-role: test_engineer' \
  -d '{
    "scene_id": "mixed_terrain_demo",
    "version": "0.1.0",
    "terrain_pack": "mixed",
    "assets": [
      {"asset_id": "checkpoint_a", "asset_type": "checkpoint", "uri": "checkpoint://A"},
      {"asset_id": "low_mu_zone", "asset_type": "forbidden_zone", "uri": "zone://low_friction"}
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
  }'
```

预期结果：响应中 `ok=true`，`state=draft`，并返回确定性的 `checksum`。

## 3. 发布场景基线

发布基线属于高风险操作，必须提供非空原因。

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/scenes/mixed_terrain_demo/0.1.0/baseline \
  -H 'content-type: application/json' \
  -H 'x-actor-id: sim-test-1' \
  -H 'x-actor-role: test_engineer' \
  -d '{"reason": "validated for task and training regression"}'
```

预期结果：响应中 `ok=true`，`state=published`，且 `is_current_baseline=true`。API 会写入一条 `scene.publish_baseline` 审计记录，并发布一条 `scene.lifecycle` 事件。

## 4. 在任务或训练计划中使用场景

任务操作者提交任务时，可以引用已发布场景：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/tasks \
  -H 'content-type: application/json' \
  -H 'x-actor-id: operator-1' \
  -H 'x-actor-role: operator' \
  -d '{
    "source_text": "避开低摩擦区，先巡检A，再巡检B，最后回到平台待命",
    "scene_ref": {"id": "mixed_terrain_demo", "version": "0.1.0"},
    "require_confirmation": true
  }'
```

算法工程师提交训练计划时，可以引用同一场景：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/training/plans \
  -H 'content-type: application/json' \
  -H 'x-actor-id: algo-1' \
  -H 'x-actor-role: algorithm_engineer' \
  -d '{
    "training_id": "train-mixed-001",
    "scene_ref": {"id": "mixed_terrain_demo", "version": "0.1.0"},
    "algorithm": "ppo_placeholder",
    "max_iterations": 100,
    "num_envs": 1,
    "seed": 42
  }'
```

如果场景不存在或已归档，API 会返回 `404 NOT_FOUND` 或 `409 STATE_CONFLICT`，并在创建任务或训练状态前拒绝请求。

## 5. 复制与归档

复制一个场景版本：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/scenes/mixed_terrain_demo/0.1.0/copy \
  -H 'content-type: application/json' \
  -H 'x-actor-id: sim-test-1' \
  -H 'x-actor-role: test_engineer' \
  -d '{"new_version": "0.2.0", "reason": "add regression variant"}'
```

归档一个场景版本：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/scenes/mixed_terrain_demo/0.2.0/archive \
  -H 'content-type: application/json' \
  -H 'x-actor-id: sim-test-1' \
  -H 'x-actor-role: test_engineer' \
  -d '{"reason": "superseded by new terrain asset version"}'
```

使用 `include_archived=true` 时，已归档场景仍可查询，但不能再用于新的任务请求或训练请求。

## 6. 校验失败示例

发布基线操作会拒绝以下情况：

- 资产 URI 为空。
- 资产 URI 以 `missing:` 开头。
- 资产 ID 重复。
- 地形包不受支持。
- 传感器采样率不在 `1..1000` Hz 范围内。
- 传感器噪声为负数。
- 域随机化参数范围包含非正值，或上界小于下界。

上述失败会返回 `422 INVALID_REQUEST`，并阻止场景成为基线。

## 7. 证据检查

使用以下接口检查运行证据：

```bash
curl -sS 'http://127.0.0.1:8000/api/v1/events' -H 'x-actor-role: auditor'
curl -sS 'http://127.0.0.1:8000/api/v1/audit' -H 'x-actor-role: auditor'
curl -sS 'http://127.0.0.1:8000/api/v1/scenes?include_archived=true' -H 'x-actor-role: auditor'
```

预期证据：

- 创建、复制、发布基线和归档操作对应的 `scene.lifecycle` 事件。
- 基线发布和归档操作对应的 `audit.record` 审计记录。
- 使用 `--state-dir` 后，API 重启仍保留已持久化的 `checksum`、`state` 和 `is_current_baseline` 字段。