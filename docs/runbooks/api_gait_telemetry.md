# API 步态遥测与 MuJoCo 本机步态验证

本手册用于验证本机 API / Web Console 链路中的步态证据是否随仿真时间推进，并确认 MuJoCo / Webots 后端仍只消费安全动作。

## 1. 命令行快速验证

```bash
PYTHONPATH=python pytest -q \
  tests/python/test_api_simulation_runner.py \
  tests/python/test_local_gait_presentation.py
```

预期结果：

- `SimulationRunSummary.gait_name` 为 `trot`、`crawl`、`cautious_trot` 或 `stand`。
- 普通前进行走时 `gait_phase > 0.0`，且长步数运行的相位大于短步数运行的相位。
- `joint_command_count == 12` 表示四条腿的髋、腿、膝 12 个名义关节目标已经进入本机仿真命令。
- `swing_foot_count + stance_foot_count == 4` 表示四个足端相位完整。

## 2. Web Console 验证

启动控制台：

```bash
PYTHONPATH=python python scripts/run_web_console.py
```

在浏览器打开 `/console/` 后：

1. 选择 `MuJoCo 本机物理仿真` + `快速无窗口` 或 `MuJoCo 可视化`。
2. 保存或加载默认混合地形场景。
3. 输入“从平台出发，避开低摩擦区，先巡检A，再巡检B，最后回到平台待命”。
4. 点击“运行任务”。

运行状态面板应出现：

- 步态：如 `小跑 / 1.79 Hz`、`爬行步态 / 0.96 Hz`。
- 足端相位：如 `摆动 2 / 支撑 2`。
- 证据输出中包含 `本机步态`、`本机步频`、`本机足端相位`、`本机关节目标数量`。

## 3. MuJoCo 展示链路注意事项

- 选择 viewer profile 时，API 会先启动或复用展示进程，再用 headless summary 生成可重复状态证据。
- MuJoCo 后端收到 `LocomotionHint` 但没有显式 `JointCommand` 时，会在后端由同一套 gait hint 派生 12 关节目标。
- 急停、暂停、人工接管和 Safe-Stand 仍通过高优先级 override 写入展示命令目录，不能由步态合成绕过。

## 4. 常见问题

- `gait_phase` 始终为 0：检查是否运行了旧代码；新链路应使用 `ObservationPacket.timestamp_ns` 生成 `SafeAction.timestamp_ns`。
- `joint_command_count` 为 0：通常说明最后一步是 `replan`、`stop` 或 `safe_stand`；可降低障碍重规划阈值或使用空障碍平地场景验证连续前进。
- MuJoCo viewer 未启动：先使用 `headless_fast` 验证 API 步态证据，再按 `docs/runbooks/sim_backends.md` 安装本机 MuJoCo 可视化依赖。