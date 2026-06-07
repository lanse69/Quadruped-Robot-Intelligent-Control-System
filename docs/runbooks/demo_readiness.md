# QRICS 本机答辩演示就绪检查运行手册

## 1. 目标

本手册用于在答辩前确认本机 MuJoCo + Webots 演示链路是否可运行，并给出缺失依赖的修复命令。检查范围覆盖：

```text
Python/API 服务依赖 -> Web Console 静态资源 -> MuJoCo -> Webots -> C++ qrics_core_runtime -> 桌面应用入口 -> 本机状态目录
```

就绪检查不会打开 MuJoCo/Webots 仿真窗口，也不会启动真实长任务；若 C++ 二进制存在，它会运行一个有步数上限的 `minimal` smoke case 来验证核心运行时可执行。

## 2. 命令行检查

在仓库根目录执行：

```bash
python scripts/check_demo_readiness.py --format markdown
```

输出 JSON：

```bash
python scripts/check_demo_readiness.py --format json
```

返回码说明：

| 返回码 | 含义 |
|---|---|
| `0` | `ready` 或 `degraded`，本机演示主链路可继续推进。 |
| `2` | `blocked`，存在必需能力缺失，先按输出命令修复。 |

## 3. Web Console 检查

启动控制台：

```bash
python scripts/run_web_console.py --host 127.0.0.1 --port 8000
```

浏览器打开：

```text
http://127.0.0.1:8000/console/
```

页面顶部“0. 演示就绪检查”会在连接 API 后自动刷新，也可以点击“检查本机环境”。

## 4. 常见修复命令

安装本机演示依赖：

```bash
python -m pip install -e ".[api,local-sim,dev]"
```

构建 C++ 核心运行时：

```bash
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug --target qrics_core_runtime
export QRICS_CPP_CORE_RUNTIME_BIN=$PWD/build/dev-gcc-debug/qrics_core_runtime
```

安装桌面应用入口：

```bash
python scripts/install_web_console_app.py install --force
```

卸载桌面应用入口：

```bash
python scripts/install_web_console_app.py uninstall
```

Webots 检查为可选降级项。若本机没有安装 Webots，可以先用 MuJoCo 完成答辩主演示；安装 Webots 后确认 `webots` 在 `PATH` 中即可。

## 5. 验收关注点

- `status=ready`：MuJoCo、API、C++ runtime、状态目录均可用；Webots 和桌面入口也可用。
- `status=degraded`：主链路可运行，但存在 Webots 等非必需能力缺失。
- `status=blocked`：缺少必需能力，通常是 MuJoCo、FastAPI/Uvicorn、C++ runtime 或状态目录不可写。

答辩前建议保存一次 Markdown 输出，作为本机部署与演示环境证据。