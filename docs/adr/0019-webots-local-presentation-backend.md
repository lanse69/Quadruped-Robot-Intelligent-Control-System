# ADR-0019 Webots 本机演示后端与 C++ 本机仿真边界

## 状态

Accepted

## 背景

当前仓库已经形成 C++ 领域模型、安全门控、任务编排、训练评测、模型治理、回放审计和 Python API / MuJoCo 本机仿真辅助层。用户本机无法承载 Isaac Sim / Isaac Lab，因此答辩演示需要以 MuJoCo + Webots 为主：MuJoCo 承担本机物理 smoke test，Webots 承担可视化演示与教学展示。

同时，系统约束要求 C++ 仍是核心开发语言。不能让仿真后端选择、运行 profile 和本机仿真契约只存在于 Python 传输层。

## 决策

1. 在 C++ 核心库中新增 `qrics::simulation::LocalBackendKind`、`LocalRuntimeProfile`、`LocalBackendDescriptor` 和 `KinematicLocalSimulationAdapter`。
2. MuJoCo、Webots、Isaac Lab 均通过统一 backend kind 和 runtime profile 描述进入核心边界，Webots 不再只是文档中的后续方向。
3. Python `qrics.sim.backends.webots_env.WebotsQuadrupedEnv` 实现与 Minimal / MuJoCo 相同的 QRICS simulation protocol。
4. Webots 后端以 packaged `.wbt` world + supervisor controller + JSON command plan 的方式接入本机 Webots 进程；测试通过 `execute_webots=False` 验证契约，不要求 CI 安装 Webots。
5. API 层 `LocalSimulationRunner` 支持 `backend="webots"`，实际答辩可通过 `scripts/run_webots_demo.py` 或 API handoff 触发。

## 影响

- C++ 核心新增本机仿真后端注册和轻量 kinematic adapter 测试，保持“C++ 为主、Python 为适配/服务层”的分工。
- Python 增加 Webots 后端、Webots 资源包、演示脚本和 dry-run 测试。
- MuJoCo 仍是本机物理后端；Webots 是本机可视化/演示后端；Isaac Lab 保留为高保真远程或后续环境后端。
- Webots 未安装时，Webots 真实进程演示会返回明确错误；dry-run 契约仍可用于开发验证。

## 验证

- `ctest` 增加 `qrics_local_simulation_adapter_test`。
- `pytest` 增加 `test_webots_backend_contract.py`。
- `scripts/check_local_sim_env.py` 增加 Webots command 检测和 QRICS Webots dry-run contract 检测。