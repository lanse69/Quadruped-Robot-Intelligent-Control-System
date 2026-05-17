# ADR-0001: 初始化工程骨架

## 状态

Accepted

## 背景

项目需要支持 C++20 主体实现、Python 工具链、仿真适配接口、测试和后续 CI。

## 决策

采用 CMake + Ninja 管理 C++ 构建；采用 pytest、ruff、black、mypy 管理 Python 测试与质量检查；先建立平台无关的工程骨架，Isaac Lab 后续通过适配层接入。

## 后果

项目可以在未安装 Isaac Lab 的电脑上完成基础构建、接口开发和单元测试。