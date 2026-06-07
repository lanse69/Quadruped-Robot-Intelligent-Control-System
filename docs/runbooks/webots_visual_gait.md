# Webots 可视化步态控制运行说明

## 目标

本说明用于验证 Webots 真实窗口中的四足机器人是否按 QRICS 任务路径命令显示腿部摆动/支撑动画。该能力服务于本机答辩演示，不改变核心安全链路：Webots controller 只消费已经由 API / C++ 控制链路生成并安全门控后的高层 `run_path` / `stop` / `safe_stand` 命令。

## 运行前提

安装项目依赖：

```bash
python -m pip install -e ".[api,local-sim,dev]"
```

安装 Webots，并保证以下任一命令能找到 Webots：

```bash
which webots
ls /snap/bin/webots
```

若 Webots 不在 PATH，可先配置：

```bash
export PATH="/path/to/Webots:${PATH}"
```

## 快速 dry-run 验证

Dry-run 不启动外部 Webots，但会验证 QRICS Webots 后端、命令映射和状态契约：

```bash
PYTHONPATH=python python scripts/run_webots_demo.py \
  --dry-run \
  --seconds 3 \
  --forward 0.22
```

## 真实 Webots 窗口验证

```bash
PYTHONPATH=python python scripts/run_webots_demo.py \
  --profile webots_fast \
  --seconds 20 \
  --forward 0.22 \
  --yaw-rate 0.04
```

预期窗口表现：

- 机身沿前进方向移动；
- 四条腿不再静止，而是按 crawl / cautious_trot / trot 视觉相位前后摆动；
- 低速或停止时腿部回到名义站立位；
- 输出 JSON 中包含 `gait_name` 和 `gait_phase`。

## Web Console 联动验证

```bash
PYTHONPATH=python python scripts/run_web_console.py
```

打开：

```text
http://127.0.0.1:8000/console/
```

选择 `Webots` 后端和 `Webots 可视化` 运行模式，保存场景，输入中文任务，例如：

```text
先巡检A，再巡检B，最后回到平台待命
```

点击运行后，API 会启动或复用 Webots presentation process，并向其 `commands/` 目录写入任务路径命令。Webots controller 会轮询该目录并执行可视化步态动画。

## 当前边界

当前 Webots 路径仍是 Supervisor 可视化动画，不是完整 Webots Robot/PROTO 的电机闭环。后续若接入真实 Webots 关节控制器，应把当前 `QRICS_LEG_*` visual gait 替换为 motor position / velocity command，但不得绕过 `SafetyShield`。