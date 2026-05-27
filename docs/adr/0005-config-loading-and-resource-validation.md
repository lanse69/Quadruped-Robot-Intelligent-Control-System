# ADR-0005: 场景配置加载与资源校验

## 状态

Accepted

## 背景

任务理解、约束检查和策略选择已经具备平台无关主链路，但当前测试仍主要依赖硬编码的 SceneProfile、PolicyCandidate 和训练参数。后续进入任务执行器、训练评测和 Isaac Lab 适配前，需要先把配置文件加载为领域模型，并在进入业务服务前输出结构化错误。

## 决策

当前阶段新增最小 YAML 子集加载器，不引入 yaml-cpp 等外部依赖。加载器只支持项目内受控配置格式：二级 key-value、简单列表对象、注释和空行。

配置加载结果进入既有领域对象：

- 场景配置加载为 SceneProfile。
- 策略配置加载为 PolicyArtifact。
- 训练配置加载为 TrainingConfig 草案。
- 非法配置通过 qrics::common::Error 返回结构化错误码。

配置加载器不接入 Isaac Lab，不做真实资产存在性检查，不访问对象存储，也不进入数据库。

## 后果

正向影响：

- TaskParser、ConstraintEngine 和后续 TaskExecutor 可以复用配置产生的场景上下文。
- 后续 Isaac Lab 适配前已有稳定的基线对象解析入口。
- 配置错误可以被单元测试覆盖，不再依赖运行期崩溃暴露。

限制：

- 当前 YAML 解析器不是通用 YAML 实现，只服务受控样例配置。
- 真实资产 URI、校验和一致性、版本冲突和对象存储访问留到 SceneService / Registry 阶段实现。