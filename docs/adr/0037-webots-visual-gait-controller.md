# ADR-0037 Webots 可视化步态控制器

## 状态

Accepted

## 背景

ADR-0036 已经把 `SafeAction`、`LocomotionHint`、足端相位和 12 关节名义位置提示贯通到本机 MuJoCo / Webots 后端。MuJoCo 侧可直接把关节提示映射到位置 actuator；Webots 侧此前主要由 Supervisor 平移 `QRICS_BASE`，窗口中四条腿是静态胶囊体，真实窗口演示仍容易被理解成底盘平移。

用户当前演示目标是本机 MuJoCo + Webots 可运行，且近期优先推进机器人行走效果。因此需要把 Webots 真实窗口从“只移动机身”升级为“机身沿任务路径移动、腿部按 gait phase 做摆动/支撑动画”。

## 决策

1. 在 Webots world 中将四条腿从匿名 `Transform` 改为带 `DEF` 的可寻址节点：`QRICS_LEG_FL`、`QRICS_LEG_FR`、`QRICS_LEG_RL`、`QRICS_LEG_RR`。
2. Webots Supervisor controller 启动后解析这些腿部节点的 `translation` 与 `rotation` 字段，在运行 spec 或 presentation command 产生速度时同步更新腿部位置和俯仰角。
3. Controller 内部只消费 QRICS 已安全门控后的高层速度/任务路径命令，不读取底层关节指令，不绕过 API / C++ Safety Shield。
4. Controller 使用与 QRICS 本机 gait bridge 同方向的地形/速度规则：站立、crawl、cautious_trot、trot；按 crawl 四相步序或 trot 对角足步序生成腿部视觉相位。
5. Webots 输出 JSON 增加 `gait_name` 与 `gait_phase`，用于调试外部 Webots 窗口是否进入了视觉步态循环。

## 影响

- Webots 真实窗口中的四足机器人不再只有机身位移；运行任务命令时，腿部会出现支撑/摆动节律与轻微机身 bob。
- Webots dry-run 的 API 契约保持不变，真实窗口展示增强不影响 CI 中无需 Webots 的测试路径。
- 当前仍是演示级 visual gait controller，不是 Webots 动力学关节控制器。后续若替换为完整 Robot/PROTO 和电机控制器，应继续保持 `SafeAction -> SimulationAdapter` 边界。

## 验证

- `tests/python/test_webots_scene_assets.py` 检查 Webots world 暴露四个可动画腿部 `DEF` 节点。
- 同一测试检查 Webots controller 存在 `_apply_leg_animation()`、步态选择和输出 `gait_name` / `gait_phase` 证据。
- `python -m py_compile python/qrics/sim/assets/webots/controllers/qrics_controller/qrics_controller.py` 验证 controller 语法。