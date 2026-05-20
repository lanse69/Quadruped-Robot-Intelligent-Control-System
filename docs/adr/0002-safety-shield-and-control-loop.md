# ADR-0002: 安全门控与占位控制闭环

## 状态

Accepted

## 背景

系统要求策略、控制器和人工指令在下发仿真适配器前必须通过安全门控。当前阶段尚不接入 Isaac Lab，但需要先固化平台无关的 `ActionProposal -> SafeAction -> SimulationAdapter::step()` 边界。

## 决策

新增 `SafetyShield` 抽象接口和 `BasicSafetyShield` 占位实现；新增 `ControlLoop::step_once()` 作为最小控制闭环。安全拒绝不视为系统失败，而是返回成功的 `ControlStepResult`，保留 `SafetyEvaluation` 与 `SafetyEvent`，同时禁止向适配器下发被拒绝动作。

## 影响

后续 Isaac Lab 适配器、策略运行时和任务编排模块均只能向控制链路提交 `ActionProposal` 或人工接管上下文，最终下发对象必须是 `SafeAction`。安全事件可以继续扩展为审计、告警和回放索引输入。