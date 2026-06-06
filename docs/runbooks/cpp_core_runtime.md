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