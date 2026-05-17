# 基于仿真环境的四足机器人智能控制系统

> Quadruped Robot Intelligent Control System  
> Simulation-based Quadruped Robot Intelligent Control System

本项目面向四足机器人仿真研发场景，构建单机器人在仿真环境中的任务执行、智能控制、安全约束、策略训练、模型治理、实验回放与审计闭环。

项目以 **C++ 为主、Python 为辅**。C++ 负责核心领域模型、控制链路、仿真适配抽象和安全约束；Python 负责 Isaac Lab 集成、训练评估脚本、实验调度和数据分析。

## 项目范围

V1.0 聚焦仿真环境内的单机器人、单仿真会话闭环。当前基线平台为 **Isaac Lab**，其他仿真平台通过适配器机制保留扩展边界。

系统覆盖以下能力：

- 仿真场景、地形、障碍物、检查点、禁行区和传感器配置管理
- 自主导航、路径跟踪、地形自适应、恢复控制和障碍规避
- Safety Shield 动作安全约束、急停、Safe-Stand 和人工接管
- 中文自然语言任务解析、TaskScript 生成、任务图编排和执行预览
- 策略训练、批量实验、标准化评测、模型门禁、发布与回滚
- 运行监控、关键事件索引、实验回放、报告导出和审计追踪
- Simulation Adapter 仿真适配接口，用于隔离上层业务和底层仿真平台

## 不包含内容

V1.0 不实现以下内容：

- 实体四足机器人底层驱动
- 真实传感器标定
- 多机器人协同与编队控制
- 面向公网的开放服务
- 商业化云平台计费
- 实体机器人闭环验收

## 架构核心

### Simulation Adapter

上层任务、控制、训练、评测、回放和审计模块通过统一仿真适配接口访问仿真能力。环境创建、场景加载、环境重置、动作下发、状态查询、观测采集、事件记录和回放元数据导出均由适配层承接。

### Safety Shield

自然语言解析、策略推理、控制器输出和人工指令不能直接下发为底层动作。所有 ActionProposal 必须经过 Safety Shield 检查，转换为 SafeAction 后才能进入仿真步进。

Safety Shield 处理的约束包括姿态角、速度、动作幅值、碰撞风险、禁行区、策略状态、急停状态和人工接管状态。

### Policy Registry 与 Gate Engine

训练生成的候选策略需要注册为 Policy Artifact，并经过标准化评测、门禁判断和审批记录后才能进入可执行状态。中间 checkpoint 不会自动替代基线策略。

### Replay 与 Audit

任务执行、训练、评测、模型状态变更、安全事件和高风险操作都会关联场景版本、策略版本、配置摘要、指标引用、回放引用和审计记录，以支持实验复现、失败样本定位和模型回滚。

## 技术栈

当前确定使用：

- C++20
- Python 3.11 / 3.12
- CMake
- Ninja / Make
- Isaac Lab / Isaac Sim
- PyTorch
- CUDA / NVIDIA Driver
- Docker
- GitHub Actions

具体第三方库会随实现阶段加入，并在依赖文件中固定版本。

## 仓库结构

```text
Quadruped-Robot-Intelligent-Control-System/
├── README.md
├── .gitignore
├── CMakeLists.txt
├── cmake/
├── configs/
│   ├── scenes/
│   ├── robot/
│   ├── safety/
│   └── training/
├── docs/
│   ├── SRS/
│   ├── Design/
│   ├── ADR/
│   └── runbooks/
├── include/
│   └── qrics/
├── src/
│   ├── core/
│   ├── simulation/
│   ├── control/
│   ├── safety/
│   ├── planning/
│   ├── training_bridge/
│   ├── registry/
│   ├── replay/
│   └── audit/
├── python/
│   └── qrics/
├── scripts/
├── tests/
│   ├── cpp/
│   └── python/
├── tools/
└── third_party/
```

目录会按开发进度逐步补齐。

## 本机环境信息采集

```bash
chmod +x scripts/collect_env.sh
./scripts/collect_env.sh
```

脚本会生成：

```text
reports/env/env_report_YYYYmmdd_HHMMSS.txt
```

脚本只采集环境信息，不安装软件，不修改系统配置。

## 开发约定

### 分支

- `main`：保持可构建、可测试
- `feature/<name>`：功能开发
- `fix/<name>`：缺陷修复
- `docs/<name>`：文档更新
- `experiment/<name>`：实验性功能

### 提交信息

提交信息采用以下格式：

```text
<type>: <中文描述>
```

常用类型：

- `feat`：新增功能
- `fix`：修复缺陷
- `docs`：文档更新
- `test`：测试相关
- `refactor`：重构
- `chore`：工程配置、依赖、脚本等维护工作

示例：

```text
feat: 添加仿真适配器接口定义
fix: 修正安全速度阈值判断逻辑
docs: 更新环境配置步骤
test: 添加 Safety Shield 单元测试
chore: 添加 CMake 基础构建配置
```

### 代码与配置

- C++ 代码使用 C++20。
- Python 代码使用类型标注。
- 领域模型、仿真适配实现和平台私有逻辑分离。
- 配置文件不写入本机绝对路径、密钥、用户名和私有目录。
- 日志不输出 token、密钥、对象存储凭据和模型签名信息。
- 高风险操作需要形成审计记录。

## 开发路线

### Phase 0：仓库与工程基础

- [x] README
- [x] .gitignore
- [x] 环境信息采集脚本
- [ ] CMake 基础骨架
- [ ] Python 包骨架
- [ ] GitHub Actions 初始门禁

### Phase 1：领域模型与接口

- [ ] SceneProfile / TaskScript / PolicyArtifact / ExperimentRun / SafetyEvent
- [ ] Simulation Adapter 抽象接口
- [ ] Observation Schema / Action Schema
- [ ] Safety Shield 基础规则
- [ ] C++ 与 Python 单元测试框架

### Phase 2：控制闭环最小原型

- [ ] Isaac Lab Adapter 最小实现
- [ ] 机器人状态查询与动作步进
- [ ] 路径跟踪控制器
- [ ] 急停与 Safe-Stand
- [ ] 控制事件与关键帧记录

### Phase 3：训练、评测与模型治理

- [ ] 训练任务配置
- [ ] 评测指标计算
- [ ] Policy Registry
- [ ] Gate Engine
- [ ] 策略发布、回滚和归档状态机

### Phase 4：回放、审计与工程化

- [ ] Replay Manifest
- [ ] KeyFrame Index
- [ ] Audit Log
- [ ] 报告导出
- [ ] CI、容器化和运行手册

## 许可证

当前未声明许可证。公开发布前需要补充 `LICENSE` 文件。

## 仓库地址

https://github.com/lanse69/Quadruped-Robot-Intelligent-Control-System
