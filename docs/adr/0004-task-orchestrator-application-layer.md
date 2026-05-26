# ADR-0004: 任务运行状态模型与 Task Orchestrator 应用层骨架

## 状态

Accepted

## 背景

当前代码已经具备中文任务解析、约束检查、策略候选选择、顺序任务图生成和执行预览。系统仍缺少一个应用层入口来承接任务提交、解析结果、操作者确认、控制交接、拒绝原因记录和取消操作。

如果直接进入 TaskExecutor 或 Isaac Lab 适配，任务输入、执行预览和操作者确认之间会缺少显式状态边界，也不利于后续 API、审计和回放接入。

## 决策

本阶段拆分为：

- `task_understanding_pipeline.hpp`：任务理解流水线，承接 TaskScript、TaskGraph 和 ExecutionPreview 的生成链路。
- `task_lifecycle.hpp`：任务生命周期状态、状态事件和 TaskSession 快照。
- `task_session_store.hpp`：TaskSessionStore 抽象接口和 InMemoryTaskSessionStore 声明。
- `in_memory_task_session_store.cpp`：内存会话存储实现。
- `task_orchestrator_service.hpp`：TaskSubmissionRequest 和 TaskOrchestratorService API。
- `task_orchestrator_service.cpp`：submit / confirm / handoff / cancel 状态流转实现。

TaskOrchestratorService 调用已有 TaskUnderstandingPipeline，并管理：

```text
Received -> Understanding -> PreviewReady / Rejected
PreviewReady -> Confirmed
Confirmed -> HandedOff
非终态 -> Cancelled
```

## 不做内容

本阶段不实现真实任务执行器，不下发控制动作，不接 Isaac Lab，不接数据库，不接 API，也不实现异步事件总线。

## 后果

后续 API 层可以直接调用 TaskOrchestratorService 完成提交、预览、确认、取消和交接。TaskExecutor 可以只接收 HandedOff 状态的 TaskGraph。审计服务可以基于 TaskLifecycleEvent 扩展为持久化审计日志。