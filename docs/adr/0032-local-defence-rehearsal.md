# ADR-0032 本机答辩端到端演练脚本

## 状态

Accepted

## 背景

系统已经具备本机演示就绪检查、Web Console 场景搭建、MuJoCo/Webots 预览、中文任务一键运行、C++ core runtime 探测、回放和审计基础能力。但答辩前仅检查依赖是否安装还不够，仍需要一条可重复、可提交、可失败定位的系统级演练链路。

答辩演示的风险主要来自模块之间的组合：场景能保存但仿真不读取、任务能解析但 handoff 不生成 run、仿真能跑但回放/审计没有证据、训练/评测状态机不能闭合等。因此需要一个不依赖浏览器人工点击的端到端脚本。

## 决策

新增 `python/qrics/demo/rehearsal.py` 与 `scripts/run_demo_rehearsal.py`。

演练脚本通过 `QricsApiApp` 应用层接口执行完整链路：

1. 创建 typed 本机场景。
2. 执行仿真预览。
3. 使用一键任务运行路径完成自然语言解析、TaskScript / TaskGraph、确认、handoff、回放与事件沉淀。
4. 查询控制状态、回放、审计和事件。
5. 下发 Safe-Stand 与 EmergencyStop，验证安全接管与审计。
6. 执行轻量训练、检查点、策略注册、标准化评测、审批、发布和基线提升。
7. 输出 JSON 与 Markdown 证据。

该脚本不替代 Web Console，而是作为答辩前自动验收和故障定位工具。Web Console 仍是现场交互演示入口。

## 约束

- 默认后端为 `minimal`，用于快速验证系统链路。
- MuJoCo/Webots 可通过参数切换，环境缺失时失败应可解释。
- 训练段只验证训练/评测/门禁状态机，不声明已经完成大规模强化学习训练。
- 脚本必须返回明确退出码：全部步骤通过为 `0`，任一步失败为 `1`。
- 输出证据不得依赖外部网络或在线 LLM。

## 影响

新增文件：

- `python/qrics/demo/rehearsal.py`
- `scripts/run_demo_rehearsal.py`
- `tests/python/test_demo_rehearsal.py`
- `docs/runbooks/demo_rehearsal.md`

该决策强化了答辩前的可复现性，使“系统是否能完整演示”从人工点击经验变为可自动验证的证据链。