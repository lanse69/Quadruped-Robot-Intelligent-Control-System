# 本机观测映射与安全回放运行手册

## 目标

用于在不运行 Isaac 的本机环境中演示 QRICS 的 MuJoCo/Webots 控制链路：场景障碍物与混合地形被映射到 `ObservationPacket`，控制层经 Safety Shield 产生 `SafeAction`，API 与回放返回可解释安全证据。

## C++ 验证

```bash
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug
ctest --preset dev-gcc-debug --output-on-failure
```

重点测试：

- `qrics_local_simulation_adapter_test`：验证本机适配器输出 `terrain_class` 与 `obstacle_state`。
- `qrics_local_control_integration_test`：验证 TaskExecutor 读取本机观测后由 Safety Shield 触发 `CollisionRisk` 并输出 `Replan`。
- `qrics_scene_config_loader_test`：验证 YAML 中的 `obstacles[]` 和矩形 `forbidden_zones[]` 能被加载和校验。

## Python/API 验证

```bash
PYTHONPATH=python python3 -m compileall -q python tests/python
PYTHONPATH=python python3 -m pytest -q
```

可选 API 依赖安装：

```bash
python -m pip install -e ".[api,dev]"
```

可选 MuJoCo 本地后端依赖：

```bash
python -m pip install -e ".[local-sim]"
```

`httpx2` 属于 dev extra 的保留依赖，不要删除。

## 演示路径

1. 创建或使用包含 `asset_type="obstacle"` 的场景。
2. 提交任务并确认执行预览。
3. 执行 handoff，API 会启动 bounded local simulation。
4. 查询控制状态：确认 `terrain_class`、`obstacle_detected`、`nearest_obstacle_distance_m`、`safety_event_count`。
5. 查询 replay：确认 `keyframes` 与 `safety_events` 中包含 `CollisionRisk`。

## 注意事项

- Minimal 后端用于快速测试和无 MuJoCo 环境的 smoke test，其 IMU/障碍观测标记为 `estimated`。
- MuJoCo 后端需要安装 `mujoco>=3.2,<4`；如果未安装，API handoff 会返回仿真交接失败并写入审计。
- Webots 后端默认可用确定性 Python 状态；真正拉起 Webots 进程需要本机安装 Webots 并启用对应执行参数。