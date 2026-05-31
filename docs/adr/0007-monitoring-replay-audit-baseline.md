# ADR-0007: 监控、回放与审计基础模型

## 状态

Accepted

## 背景

当前代码已经完成任务理解、任务生命周期、配置加载、任务执行器、占位策略运行时和最小控制闭环。`TaskExecutor` 已经能够产出 `TaskExecutionSnapshot`，`SafetyShield` 能产出 `SafetyEvent`，`SimulationAdapter::step()` 能返回 `AdapterStepResult / RobotState`。

如果下一步直接接 Isaac Lab，运行状态、告警、关键帧和审计证据仍没有稳定的领域模型承接。设计文档要求监控、回放与实验审计负责状态刷新、告警去重、关键事件索引、回放片段、实验报告、追加式审计与审计检索；安全事件和高风险操作必须进入可追溯链路。

## 决策

新增平台无关的监控、回放与审计基础模型：

- `events/event_sink.hpp` 与 `src/events/in_memory_event_sink.cpp`：定义统一事件记录、事件查询和内存事件沉淀实现。
- `monitoring/telemetry.hpp/.cpp`：把 `TaskExecutionSnapshot` 转换为 `TelemetryFrame`，再转换为可查询 `EventRecord`。
- `monitoring/alert_event.hpp/.cpp`：把 `SafetyEvent` 转换为 `AlertEvent` 和事件记录。
- `replay/keyframe_index.hpp/.cpp`：把安全事件转换为关键帧索引，支持按 `run_id`、时间窗、事件类型查询。
- `replay/replay_manifest.hpp/.cpp`：定义回放分段与回放清单，校验分段和关键帧必须与 `run_id` 一致。
- `audit/audit_log.hpp/.cpp`：定义审计日志、审计查询和内存审计存储；高风险操作没有原因时拒绝写入。

## 不做内容

本阶段不接数据库、对象存储、消息总线、WebSocket、HTTP API、报告导出和 Isaac Lab。所有存储均为内存实现，只用于固定领域模型和测试约束。

## 后果

后续 Control Service 可以把 `TaskExecutionSnapshot`、`SafetyEvent` 和 `AdapterStepResult` 沉淀为遥测、告警、关键帧与审计事件。后续 Isaac Lab 适配接入后，只需要把真实运行事件映射到本阶段的模型，不需要改变任务执行与安全门控语义。