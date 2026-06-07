# C++ 核心任务运行时运行手册

## 1. 目标

本手册用于验证 QRICS 的 C++ 核心控制闭环可以脱离 Web 前端独立运行，并能向 Python API / Web Console 提供自检证据。该路径覆盖：

```text
TaskGraph -> TaskExecutor -> PolicyRuntime -> LocalPlanner -> SafetyShield -> SafeAction -> SimulationAdapter
```

该路径用于证明 C++ 是核心任务执行与安全门控层，Python 主要承担 API、Web Console、桌面入口和 MuJoCo/Webots 展示辅助。

## 2. 构建

```bash
cd ~/Documents/sim_quadruped_rebot_control/Quadruped-Robot-Intelligent-Control-System
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug
```

构建完成后可执行文件位于：

```text
build/dev-gcc-debug/qrics_core_runtime
```

## 3. 直接运行 C++ runtime

```bash
./build/dev-gcc-debug/qrics_core_runtime \
  --run-id cpp_demo_run \
  --backend mujoco \
  --profile headless_fast \
  --terrain mixed_terrain_pack \
  --steps 180 \
  --task-path 'A:0.85:0.25:0.35:0.3,B:1.65:-0.25:0.35:0.3,platform:0:0:0.35:0'
```

输出为 JSON，关键字段包括：

- `state`：`running`、`succeeded`、`paused`、`failed` 等控制状态。
- `executed_step_count`：C++ `TaskExecutor` 控制步数。
- `adapter_step_count`：实际下发到 `SimulationAdapter::step()` 的步数。
- `base_position`：机器人底座位置。
- `terrain_class`：地形识别结果。
- `obstacle_detected` / `nearest_obstacle_distance_m`：障碍感知证据。
- `safety_events` / `keyframes`：Safety Shield 触发证据。
- `nodes`：TaskGraph 节点执行状态。

## 4. Python 桥接自检

```bash
python scripts/run_cpp_core_runtime_demo.py
```

若二进制未构建，会返回 `available=false` 并提示构建命令；若已构建，会返回 `available=true` 和 C++ runtime 输出摘要。

也可以通过环境变量指定二进制路径：

```bash
export QRICS_CPP_CORE_RUNTIME_BIN=$PWD/build/dev-gcc-debug/qrics_core_runtime
python scripts/run_cpp_core_runtime_demo.py
```

## 5. HTTP / Web Console 自检

启动 Web Console：

```bash
python scripts/run_web_console.py --host 127.0.0.1 --port 8000
```

HTTP 调用：

```bash
curl http://127.0.0.1:8000/api/v1/sim/core-runtime
```

Web Console 操作：

1. 打开 `http://127.0.0.1:8000/console/`。
2. 点击“C++核心自检”。
3. 在“运行状态 / 回放 / 审计”区域查看 C++ runtime 是否可用、二进制路径、执行命令和运行摘要。

## 6. 回归验证

```bash
ctest --preset dev-gcc-debug --output-on-failure
python -m pytest
```

本阶段新增 C++ 测试目标：

```text
qrics_cpp_core_runtime_test
```

新增 Python 测试：

```text
test_cpp_core_runtime_bridge.py
```

## 7. 与 MuJoCo/Webots 演示链路的关系

C++ runtime 负责证明核心任务执行、安全门控和统一适配接口可以独立运行。Web Console 的“预览 / 打开仿真”和“运行任务”仍由 Python 本机 MuJoCo/Webots 后端负责打开 viewer、绑定用户搭建场景、写入展示命令通道和生成回放审计证据。

答辩演示建议顺序：

1. 用 Web Console 搭建或加载场景。
2. 点击“C++核心自检”，说明核心控制闭环由 C++ 实现并可输出 JSON 证据。
3. 选择 MuJoCo 或 Webots，点击“预览 / 打开仿真”。
4. 输入中文任务并点击“运行任务”，展示窗口自动打开或复用，机器人按任务路径运动。
## 8. 自定义场景几何与一键任务运行

本阶段后，`qrics_core_runtime` 不再只能运行内置默认场景。命令行支持将 Web Console / API 保存的 typed scene geometry 显式传入 C++ 核心运行时：

```bash
./build/dev-gcc-debug/qrics_core_runtime \
  --run-id cpp_custom_scene \
  --backend mujoco \
  --profile headless_fast \
  --scene-id local_demo_scene \
  --scene-version 0.1.0 \
  --terrain mixed_terrain_pack \
  --steps 180 \
  --clear-default-assets \
  --obstacle 'box_1:box:0.80:0.20:0.20:0.30:0.30:0.30:0.15:0.30' \
  --forbidden-zone '低摩擦区:2.0:-0.8:0;3.0:-0.8:0;3.0:0.8:0;2.0:0.8:0' \
  --task-path 'A:0.85:0.25:0.35:0.3,platform:0:0:0.35:0'
```

新增参数说明：

| 参数 | 说明 |
|---|---|
| `--clear-default-assets` | 清空内置 demo 障碍、检查点和禁行区，使后续参数完全代表用户保存场景。 |
| `--obstacle id:type:x:y:z:sx:sy:sz:radius:height` | 注入障碍物。`type` 支持 `box`、`cylinder`、`sphere`。 |
| `--checkpoint id:x:y:z:dwell` | 注入检查点元数据。任务目标实际由 `--task-path` 驱动。 |
| `--forbidden-zone id:x:y:z;x:y:z;...` | 注入多边形禁行区，供 Safety Shield 执行禁行区硬约束检查。 |

`run_local_task()` 输出新增字段：

```json
{
  "scene_id": "local_demo_scene",
  "scene_version": "0.1.0",
  "task_target_count": 2,
  "scene_obstacle_count": 1,
  "scene_checkpoint_count": 0,
  "scene_forbidden_zone_count": 1
}
```

Python API 的 `POST /api/v1/tasks/run` 与 `POST /api/v1/tasks/{task_id}/handoff` 会在执行本机 MuJoCo/Webots 展示链路时同步调用 C++ 核心运行时。若已构建 `qrics_core_runtime`，接口响应的 `status.core_runtime_available=true`，并在 `status.core_runtime_summary` 中返回 C++ 命令与 JSON 摘要。若尚未构建二进制，该字段返回 `available=false` 和构建提示，不阻断 Web Console 本机演示链路。

## 9. C++ 回放证据落盘

本阶段新增 `--evidence-dir`，用于让 C++ 核心运行时在执行任务时同步生成回放证据文件，而不是只把摘要返回给 Python API：

```bash
./build/dev-gcc-debug/qrics_core_runtime \
  --run-id cpp_evidence_demo \
  --backend mujoco \
  --profile headless_fast \
  --steps 80 \
  --evidence-dir runtime/core-runtime-evidence
```

输出 JSON 会新增以下字段：

```json
{
  "replay_manifest_uri": "file://.../cpp_evidence_demo_core_replay_manifest.json",
  "replay_manifest_path": ".../cpp_evidence_demo_core_replay_manifest.json",
  "replay_segment_uri": "file://.../cpp_evidence_demo_core_segment.jsonl",
  "replay_segment_path": ".../cpp_evidence_demo_core_segment.jsonl",
  "replay_keyframe_count": 0
}
```

生成文件：

| 文件 | 说明 |
|---|---|
| `<run_id>_core_replay_manifest.json` | 由 C++ `ReplayManifestWriter` 生成，包含 runId、sceneRef、policyRef、segment 和 safety keyframes。 |
| `<run_id>_core_segment.jsonl` | C++ 核心运行段证据，记录 run 状态、控制步数、adapter step 数和风险值。 |

通过 `scripts/run_web_console.py` 或桌面入口启动时，C++ 证据目录默认为：

```text
<state-dir>/core_runtime_evidence
```

因此 Web Console 中“一键运行任务”返回的 `status.core_runtime_summary.summary.replay_manifest_path` 可以直接证明当前任务不仅经过 Python MuJoCo/Webots 展示链路，也经过 C++ `TaskExecutor -> SafetyShield -> SimulationAdapter -> ReplayManifestWriter` 证据落盘链路。