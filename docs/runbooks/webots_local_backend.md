# QRICS Webots 本机演示后端运行手册

## 1. 定位

Webots 后端用于本机可视化答辩演示。它与 MuJoCo 共享 QRICS Simulation Adapter 语义：

```text
SafeAction -> WebotsCommandFrame -> Webots world/controller -> RobotState / ObservationPacket
```

MuJoCo 当前作为本机真实物理 smoke test 后端，Webots 作为本机可视化展示后端。二者都不改变上层任务、控制、安全门控、训练评测、回放审计接口。

## 2. 环境安装

### 2.1 Python 开发环境

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[api,local-sim,dev]"
```

`dev` extra 不再包含 `httpx2`。HTTP 测试使用官方 `httpx`。

### 2.2 Webots

Linux 常见安装方式之一：

```bash
sudo snap install webots
```

或从 Webots 官方安装包安装后确保命令可被找到：

```bash
which webots
# 或确认 /snap/bin/webots 存在
```

## 3. 检查本机后端

```bash
python scripts/check_local_sim_env.py
```

应重点查看：

```text
mujoco: OK
webots_command: OK 或 MISSING
webots_qrics_contract: OK
```

`webots_qrics_contract` 是 QRICS dry-run 契约检查，不依赖外部 Webots 进程。`webots_command` 为真实 Webots 演示前置条件。

## 4. 运行 Webots 演示

先验证 QRICS 侧 dry-run：

```bash
python scripts/run_webots_demo.py --dry-run --seconds 3
```

启动真实 Webots 演示：

```bash
python scripts/run_webots_demo.py --profile webots_fast --seconds 12
```

脚本会使用包内资源：

```text
python/qrics/sim/assets/webots/worlds/qrics_demo.wbt
python/qrics/sim/assets/webots/controllers/qrics_controller/qrics_controller.py
```

后端会生成临时 Webots 工作目录、写入 QRICS 命令 JSON，并通过环境变量传给 Webots supervisor controller。

## 5. API handoff 使用 Webots

应用层 runner 已支持 Webots：

```python
from qrics.api.simulation_runner import LocalSimulationRunner, SimulationRunRequest

summary = LocalSimulationRunner().run(
    SimulationRunRequest(
        run_id="demo_webots",
        backend="webots",
        runtime_profile="webots_fast",
        step_count=20,
        forward_velocity_mps=0.22,
    )
)
print(summary)
```

未安装 Webots 时，可用 dry-run 验证 API 集成：

```python
summary = LocalSimulationRunner(webots_execute=False).run(
    SimulationRunRequest(run_id="demo_webots_dry", backend="webots", runtime_profile="webots_fast")
)
```

## 6. 故障处理

| 现象 | 处理 |
|---|---|
| `WEBOTS_BINARY_NOT_FOUND` | 安装 Webots，或确认 `webots` 在 `PATH` 中，或使用 `--dry-run`。 |
| Webots 窗口无法显示 | 使用本机图形桌面运行；远程无 GUI 环境先使用 `--dry-run`。 |
| Webots 启动后无运动 | 检查 controller 是否能读取 `QRICS_WEBOTS_RUN_SPEC`；重新运行脚本并查看标准错误。 |
| API handoff Webots 失败 | 先直接执行 `python scripts/run_webots_demo.py --dry-run --seconds 3`，再执行真实 Webots 演示。 |

## 7. 验证命令

```bash
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug
ctest --preset dev-gcc-debug --output-on-failure
python -m pytest tests/python/test_webots_backend_contract.py
python scripts/run_webots_demo.py --dry-run --seconds 1
```