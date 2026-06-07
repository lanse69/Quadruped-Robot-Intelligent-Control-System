# 本机步态行走展示运行说明

## 目标

本说明用于在本机 MuJoCo / Webots 演示链路中验证四足机器人行走效果。当前实现把 `SafeAction` 中的 `LocomotionHint`、足端相位和 12 关节名义位置提示传入本机仿真后端，用于展示平地 trot、坡面/碎石 cautious_trot、低摩擦/楼梯 crawl 和站立状态。

## 运行前提

基础开发安装：

```bash
python -m pip install -e ".[api,local-sim,dev]"
```

MuJoCo 演示需要本机可导入 `mujoco`。Webots 演示如果不安装外部 Webots，可使用 `--dry-run` 验证 QRICS 后端契约；需要可视化窗口时应安装并确保 `webots` 可执行程序在 PATH 或 `/snap/bin/webots`。

## MuJoCo 本机演示

无窗口快速验证：

```bash
PYTHONPATH=python python scripts/run_local_sim_demo.py \
  --profile headless_fast \
  --seconds 3 \
  --forward 0.25 \
  --yaw-rate 0.08
```

带 viewer 演示：

```bash
PYTHONPATH=python python scripts/run_local_sim_demo.py \
  --profile balanced_visual \
  --viewer \
  --seconds 20 \
  --scene-json examples/local_demo_scene.json
```

## Webots 本机演示

Dry-run 契约验证：

```bash
PYTHONPATH=python python scripts/run_webots_demo.py \
  --dry-run \
  --seconds 3 \
  --forward 0.22
```

真实 Webots 窗口演示：

```bash
PYTHONPATH=python python scripts/run_webots_demo.py \
  --seconds 20 \
  --scene-json examples/local_demo_scene.json
```

## API / Web Console 联动

```bash
PYTHONPATH=python python scripts/run_web_console.py
```

浏览器打开 `http://127.0.0.1:8000/console/`，选择 `mujoco` 或 `webots` 后端，保存场景并运行中文任务。API handoff 会向展示进程写入路径命令；展示脚本会按当前观测地形为每一步 SafeAction 补充步态提示。

## 预期证据

- `SafeAction.locomotion_hint.gait_type` 出现 `trot`、`cautious_trot`、`crawl` 或 `stand`。
- `SafeAction.joint_commands` 包含 12 个名义关节目标。
- Minimal / Webots dry-run 的 `RobotState.contacts` 至少能区分摆动足和支撑足。
- MuJoCo 后端在有 actuator 的情况下把关节目标映射到 `*_hip_pos`、`*_thigh_pos`、`*_calf_pos`。
- C++ 本机适配器会按地形/步态降低前进速度并更新 body height/contact force。


## Webots 视觉步态增强

当前 Webots world 已把四条腿暴露为 `QRICS_LEG_FL`、`QRICS_LEG_FR`、`QRICS_LEG_RL`、`QRICS_LEG_RR` 四个可寻址 `Transform`。真实 Webots 窗口运行时，Supervisor controller 会按任务路径命令、速度和地形生成 visual gait phase，并同步更新腿部 `translation` / `rotation`。

这一步不改变安全边界：Webots controller 只消费 presentation command channel 写入的高层 `run_path` / `stop` / `safe_stand` 命令，不接收也不生成底层关节控制指令。需要单独验证时参考 `docs/runbooks/webots_visual_gait.md`。

## 当前边界

当前桥接不是完整 MPC / RL 全身控制器。它用于本机答辩演示和工程闭环验证，保证任务执行、安全门控、仿真适配和回放证据能看到一致的步态字段。后续可在不改变 `SafeAction` / `SimulationAdapter` 契约的前提下替换为真实策略模型或更完整的 GaitController。