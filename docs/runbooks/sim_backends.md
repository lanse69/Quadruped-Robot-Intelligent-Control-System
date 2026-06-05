# 本机仿真后端运行手册

## 1. 目标

本手册说明如何在本机运行 QRICS 的 MuJoCo 后端，并解释 MuJoCo、Webots、Isaac Lab 的定位。

## 2. 后端定位

| 后端 | 定位 | 当前状态 |
| --- | --- | --- |
| MuJoCo | 本机主力真实物理后端 | 已接入，支持物理步进和基础状态观测 |
| Webots | 本机可视化演示后端 | 已接入 QRICS simulation protocol、`.wbt` world、supervisor controller、dry-run 契约与演示脚本 |
| Isaac Lab | 高保真需求/设计基线 | 保留契约和远程/高配接入路线 |
| MinimalQuadrupedEnv | 契约测试后端 | 仅测试生命周期和接口，不作真实演示 |

## 3. 安装与检查环境

本机真实物理后端需要安装 MuJoCo Python 包。当前推荐使用项目 extra 安装：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install -e ".[local-sim]" pytest ruff black mypy
```

检查环境：

```bash
source .venv/bin/activate
python scripts/check_local_sim_env.py
```

报告中 `mujoco_physics_step` 应为 `ok`。

## 4. 运行默认演示

```bash
python scripts/run_local_sim_demo.py --profile balanced_visual --seconds 15 --viewer
```

## 5. 无窗口快速检查

```bash
python scripts/run_local_sim_demo.py --profile headless_fast --seconds 5
```

## 6. 不流畅时的调参顺序

不要直接关闭所有仿真能力。按以下顺序降低负载：

1. 降低窗口分辨率到 1024x720。
2. 关闭录制，只保留 viewer。
3. 降低 camera preview 频率或关闭 camera preview。
4. 减少障碍物和复杂材质。
5. 增大 control_decimation。
6. 从 `balanced_visual` 切换到 `headless_fast`。

## 7. 常见问题

### MuJoCo 可以导入，但 viewer 打不开

优先用 `headless_fast` 验证物理步进，然后检查 OpenGL / GLFW / 桌面会话。可尝试：

```bash
glxinfo | grep -E "OpenGL vendor|OpenGL renderer|OpenGL version"
```

### EGL / OSMesa 失败

物理步进不依赖渲染。先确保测试和控制闭环可运行，再处理离屏截图或录屏。

### Isaac Lab 未安装是否阻断本阶段

不阻断。本阶段主目标是本机 MuJoCo 真实物理后端和 Webots 可视化演示后端。Isaac Lab 仍作为基线平台和远程高配后端保留。

## 8. 答辩建议

现场优先运行：

```bash
python scripts/run_local_sim_demo.py --profile balanced_visual --seconds 15 --viewer
```

同时准备一段提前录制的 `rich_demo` 视频，避免现场显卡、桌面会话或投屏导致 viewer 不稳定。