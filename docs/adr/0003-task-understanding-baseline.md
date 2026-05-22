# ADR-0003: 任务理解与任务图编排基础实现

## 状态

Accepted

## 背景

当前代码已经具备领域模型、SimulationAdapter 抽象接口、Safety Shield 和最小 ControlLoop。下一步需要把中文任务输入转换为可校验、可预览、可交给后续控制服务使用的 TaskScript 与 TaskGraph。

## 决策

本阶段实现平台无关的任务理解基础链路：

- 中文规则解析器生成 TaskScript。
- 约束检查器校验路径点、速度、超时、禁行区引用。
- 策略选择器仅允许 Released / Baseline 策略进入候选结果。
- 顺序任务图规划器生成 MoveTo / Dwell / ReturnHome / Stop 节点。
- 执行预览输出策略选择理由和风险摘要。

## 后果

后续可以逐步替换规则解析器为 LLM / VLM 解析器，替换规则策略选择为策略注册中心查询，替换顺序任务图为更复杂的任务规划器；上层仍保持 TaskScript、TaskGraph、ExecutionPreview 作为交付对象。