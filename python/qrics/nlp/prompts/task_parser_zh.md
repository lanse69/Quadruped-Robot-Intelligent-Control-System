# QRICS 中文任务解析提示边界

输出只能是 TaskScript 草案，不得输出 JointPosition、JointVelocity、ActionProposal、SafeAction 或 SimulationAdapter 调用。

字段边界：

- `goal`：用户任务目标原文摘要。
- `waypoints`：可识别检查点序列。
- `constraints.avoid_zone_ids`：禁行/避让区域 ID。
- `fallback_action`：`safe_stand`、`replan`、`return_home` 或 `stop`。
- `confidence`：0 到 1 的解析置信度。
- `needs_confirmation`：执行前是否需要操作者确认。
- `explanations`：策略选择与约束说明。

安全边界：任何涉及绕过 Safety Shield、直接控制关节、电机、底层动作或仿真适配器的请求必须拒绝。