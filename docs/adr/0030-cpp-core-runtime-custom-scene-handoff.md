# ADR-0030：C++ 核心运行时接收 Web Console 自定义场景并绑定一键任务运行

## 状态

Accepted

## 背景

前一阶段已经提供 `qrics_core_runtime` 和 Web Console “C++核心自检”入口，但自检仍偏向固定内置场景。答辩演示需要证明用户在 Web Console 中选择仿真软件、搭建场景、保存场景并点击“运行任务”后，核心任务执行链路不是仅由 Python 示例逻辑完成，而是能把相同场景几何、禁行区和任务路径交给 C++ 核心运行时。

## 决策

1. 扩展 `qrics_core_runtime` 命令行契约，新增 `--clear-default-assets`、`--obstacle`、`--checkpoint` 和 `--forbidden-zone` 参数。
2. 扩展 `LocalTaskRunSummary`，输出 scene id/version、任务目标数、障碍物数、检查点数和禁行区数。
3. 扩展 Python `qrics.api.core_runtime`，提供 `CoreRuntimeRunRequest`、typed geometry 编码和 `run_core_runtime_task()`。
4. `QricsApiApp.handoff_task()` 在本机 MuJoCo/Webots/minimal summary 之外同步执行 C++ 核心运行时；成功或缺失二进制均写入 `ControlStatusResponse` 的 `core_runtime_*` 字段。
5. Web Console 任务输出展示 C++ 运行时是否执行、C++ 任务状态、C++ 场景障碍数量和禁行区数量。

## 影响

- 用户保存的 typed obstacles 和 no-go-zone 现在会同时进入 Python 展示后端和 C++ 核心运行证据。
- 未构建 C++ 二进制时不阻断演示；状态响应提供明确构建提示。
- C++ 不直接链接 MuJoCo/Webots SDK，仍使用平台无关的 `KinematicLocalSimulationAdapter` 作为核心契约证明；窗口打开、进程保持和命令通道仍由 Python 本机展示层负责。

## 验证

- C++：`qrics_cpp_core_runtime_test` 覆盖新增 summary 计数字段。
- Python：`test_run_core_runtime_task_passes_custom_scene_geometry` 覆盖自定义场景参数编码；`test_one_click_task_run_includes_cpp_core_runtime_summary` 覆盖一键任务运行响应中的 C++ 证据。