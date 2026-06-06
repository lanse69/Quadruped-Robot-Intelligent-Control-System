# ADR-0029：C++ 核心任务运行契约与 Web/API 自检入口

## 状态

Accepted

## 背景

当前系统已经具备 Web Console、FastAPI、MuJoCo/Webots 本机展示后端、自然语言任务解析、一键任务运行、回放与审计链路。答辩演示链路可通过 Python 应用层打开本机仿真窗口并下发任务路径，但项目定位要求 C++ 是主要和核心开发语言。若 C++ 只停留在库级单元测试，演示时难以证明核心控制闭环确实可独立运行。

需求和设计文档强调：任务解析和策略输出不得绕过 Safety Shield，控制动作下发前必须进入安全门控；仿真平台差异应通过统一适配接口隔离；任务执行、控制安全、回放审计需要形成闭环证据。因此需要把 C++ `TaskExecutor -> PolicyRuntime -> SafetyShield -> SimulationAdapter` 链路封装为一个可执行、可测试、可被 API/Web Console 探测的运行契约。

## 决策

新增 C++ 本机任务运行引擎和命令行入口：

```text
LocalTaskRunRequest
  -> run_local_task()
  -> KinematicLocalSimulationAdapter
  -> TaskExecutor
  -> RuleBasedPolicyRuntime
  -> SimpleLocalPlanner
  -> BasicSafetyShield
  -> SafeAction
  -> SimulationAdapter::step()
  -> LocalTaskRunSummary JSON
```

新增可执行文件：

```text
qrics_core_runtime
```

该入口支持：

- `--backend minimal|mujoco|webots`：复用 C++ 本机后端枚举和适配器配置；当前 C++ 路径使用运动学本机适配器，不直接链接 MuJoCo/Webots SDK。
- `--profile headless_fast|balanced_visual|webots_fast|rich_demo`：复用 runtime profile 名称，保持和 Python/Web Console 展示配置一致。
- `--terrain`：指定场景地形。
- `--task-path id:x:y[:z[:dwell]],...`：指定任务路径点和驻留时间。
- 输出 JSON：包含运行状态、步数、机器人位置、地形识别、障碍感知、安全事件、关键帧和节点状态。

Python API 增加轻量桥接模块 `qrics.api.core_runtime`，用于定位并运行已构建的 C++ 可执行文件。HTTP 增加：

```text
GET /api/v1/sim/core-runtime
```

Web Console 增加“C++核心自检”按钮，用于显示 C++ runtime 是否可用以及其 JSON 运行证据。

## 约束

- Python API 不把 C++ runtime 作为强制启动依赖。未构建 C++ 可执行文件时，接口返回 `available=false` 和构建提示，不阻断 Web Console 主演示链路。
- C++ runtime 不绕过 Safety Shield，不直接输出底层关节动作；所有动作仍为 `ActionProposal -> SafetyShield -> SafeAction -> SimulationAdapter::step()`。
- C++ runtime 当前是核心控制契约和本机 smoke runner，不替代 Python 的 MuJoCo/Webots viewer 打开、命令通道和桌面化 UI。
- 真实 MuJoCo/Webots SDK 绑定仍保留在 Python 本机后端中；C++ 侧保持可在普通 CMake 环境构建的低依赖核心闭环。

## 影响

新增/修改：

- `include/qrics/runtime/local_task_run_engine.hpp`
- `src/runtime/local_task_run_engine.cpp`
- `apps/qrics_core_runtime.cpp`
- `tests/cpp/test_cpp_core_runtime.cpp`
- `python/qrics/api/core_runtime.py`
- `scripts/run_cpp_core_runtime_demo.py`
- `GET /api/v1/sim/core-runtime`
- Web Console “C++核心自检”入口

验证方式：

```bash
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug
ctest --preset dev-gcc-debug --output-on-failure
python scripts/run_cpp_core_runtime_demo.py
python -m pytest
```