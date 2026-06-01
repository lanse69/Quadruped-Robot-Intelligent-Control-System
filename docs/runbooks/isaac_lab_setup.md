# Isaac Lab 接入运行手册草案

## 当前状态

当前仓库只提供 Python 侧 Isaac Lab Adapter 契约和 `MinimalQuadrupedEnv` 占位后端。默认测试不依赖 Isaac Sim / Isaac Lab，不要求本机具备 GPU 仿真环境。

## 环境原则

真实 Isaac Lab 环境应与项目工程开发环境隔离：

- 工程开发环境继续用于 C++ 构建、Python 单元测试、格式化和静态检查。
- Isaac Lab 环境单独使用 Python 3.11、CUDA、Isaac Sim / Isaac Lab 及其依赖。
- CI 默认不安装 Isaac Lab，只跑契约测试。
- 真实 Isaac Lab 测试后续放入单独的 GPU / 容器 / 远程工作站流程。

## 接入顺序

1. 保持当前 `IsaacLabAdapter` 生命周期语义不变。
2. 新增真实 Isaac Lab backend，不删除 `MinimalQuadrupedEnv`。
3. 将真实环境的 reset / observe / step 输出先映射为 raw observation/state 字典。
4. 通过 `observation_mapper.py` 转换为 `ObservationPacket` 和 `RobotState`。
5. 通过 `action_mapper.py` 将 `SafeAction` 转为真实仿真动作。
6. 先验证最小 reset，再验证 stop / safe_stand / body_velocity。
7. 最后接入任务执行器链路。

## 禁止事项

- 不允许上层任务服务直接调用 Isaac Lab 私有对象。
- 不允许 `ActionProposal` 绕过 `SafetyShield` 进入 adapter。
- 不允许 `Rejected SafeAction` 映射为实际动作。
- 不允许把 Isaac Lab 大依赖加入默认 CI。
- 不允许把真实仿真路径、缓存、模型二进制或本机环境报告提交到仓库。