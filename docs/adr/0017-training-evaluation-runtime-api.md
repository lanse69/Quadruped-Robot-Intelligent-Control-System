# ADR 0017: Training/evaluation runtime evidence API

## 状态

Accepted

## 背景

需求规格说明书要求训练任务可追踪、可恢复、可查询，标准化评测需要在统一基准集上产出成功率、碰撞率、轨迹偏差、能耗代理等指标，并将候选策略与当前基线自动对比后进入模型门禁。设计说明书同时要求训练计划、检查点、评测报告、门禁结论、策略状态和审计记录形成可串联证据链。

当前代码已经具备 `MetricCalculator`、`GateEngine`、`PolicyRegistry`、FastAPI / WebSocket 服务化入口、RBAC 单一事实源、SQLite Repository 和场景资源 API。但训练 API 之前只支持创建 `queued` 任务，不能记录训练配置摘要、运行状态、检查点、训练完成产物、标准化评测报告和策略 gate 状态更新。

## 决策

本阶段在 API 应用层实现轻量训练/评测运行态闭环：

- `TrainingPlanPayload` 增加奖励配置版本、域随机化模板、检查点间隔、资源配额和备注。
- `TrainingJobResponse` 持久化 `config_hash`、当前迭代、检查点数量、最近检查点 URI 和失败原因。
- 训练任务状态流转固定为 `queued -> running -> succeeded`，以及 `queued/running -> failed/cancelled`。
- `complete_training_job` 将成功训练产物注册为候选策略，并保留工件 URI、校验和和指标摘要。
- `EvaluationRunPayload` 与 `EvaluationReportResponse` 表达标准化评测输入、候选指标、baseline 对比、门禁结论和回放引用。
- 当前轻量门禁阈值固定为 `success_rate >= 0.80`、`collision_rate <= 0.05`、`tracking_error_m <= 0.30`、`hard_constraint_violation_count == 0`。
- `run_standard_evaluation` 生成评测报告并同步更新策略为 `gate_passed` 或 `gate_failed`。
- `QricsRepository`、`InMemoryRepository` 与 `SQLiteQricsRepository` 增加训练任务列表和评测报告持久化接口。
- FastAPI 暴露训练任务读取、启动、检查点、完成、失败、取消和评测报告查询接口。
- RBAC 单一事实源加入 `training.read/start/checkpoint/complete/fail/cancel` 与 `evaluation.run/read` 权限。

## 后果

训练、评测、模型治理和审计之间形成了不依赖真实 Isaac Lab 的可测试证据链，可满足本机演示、API 契约测试和 SQLite 持久化回归。真实强化学习后端、GPU 队列、Isaac Lab 并行环境启动、检查点自动恢复、审批工作流和报告导出仍作为后续阶段接入，不在本 ADR 中声明完成。