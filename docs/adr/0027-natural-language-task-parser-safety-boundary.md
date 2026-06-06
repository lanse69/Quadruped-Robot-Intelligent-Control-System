# ADR-0027：自然语言任务解析与 AI 安全边界

## 状态

Accepted

## 背景

当前本机演示链路已经具备 Web Console、场景搭建、MuJoCo / Webots 后端选择、任务 handoff、回放与审计查询。下一处影响答辩演示完整性的缺口是：应用 API 的任务入口仍主要依赖少量 `A / B / 平台` 文本匹配，不能稳定展示 TaskScript、TaskGraph、解析置信度、约束与拒绝原因。

需求中要求自然语言任务理解和任务规划编排；设计中要求 AI / NLP 只能生成任务脚本、策略建议与解释信息，不能绕过 Safety Shield 或直接下发动作。因此本阶段在 Python 应用层新增确定性 NLP parser，同时保持 C++ 控制、安全门控和仿真适配为核心执行边界。

## 决策

新增 `qrics.nlp` 包，包含：

- `schema.py`：定义 `TaskParseCatalog`、`WaypointAlias`、`AvoidZoneAlias`、`ParsedTaskDraft` 等语义对象。
- `rule_based_parser.py`：实现确定性中文规则解析器，支持巡检点顺序、禁行/避让区域、驻留时间、返回平台、重规划和停止语义。
- `task_parser_adapter.py`：将 API `SceneProfilePayload` 中的 checkpoint / no_go_zone 资产转为 parser catalog，使用户在 Web Console 中保存的场景能参与任务理解。
- `prompts/task_parser_zh.md` 与 `examples/demo_tasks.json`：固定后续 LLM adapter 的输出边界和示例，不在当前版本引入网络模型依赖。

API `TaskPreviewResponse` 扩展以下字段：

```text
parser_version
parse_confidence
constraints
fallback_action
explanation
task_script
task_graph
rejection_reason
waypoint_details
```

任务提交链路改为：

```text
source_text + scene_ref
  -> qrics.nlp.parse_task_source()
  -> TaskScript draft / TaskGraph preview
  -> operator confirmation
  -> handoff_task()
  -> SimulationRunner
  -> Safety Shield / replay / audit
```

## 安全边界

自然语言解析器只输出 `TaskScript` 草案和可解释信息，不输出以下对象：

- `JointPosition`
- `JointVelocity`
- `ActionProposal`
- `SafeAction`
- `SimulationAdapter` 调用

包含“绕过安全”“跳过安全”“直接下发动作”“底层关节”“直接控制电机”等语义的输入会被拒绝，API 返回 `state=rejected` 与 `rejection_reason`。即使解析成功，控制动作仍必须通过既有控制链路和 Safety Shield。

## 影响

- Web Console 任务运行输出会展示解析器版本、置信度、约束、回退动作和解释。
- SQLite Repository 会持久化扩展后的任务预览字段，避免重启后丢失解析证据。
- 现有任务、控制、回放和审计接口保持兼容；`waypoints` 仍保留为字符串数组，同时新增 `waypoint_details`。
- 本阶段不接入在线 LLM，不新增外部 API Key，不依赖 Isaac Lab。

## 验证

新增测试：

```bash
python -m pytest tests/python/test_rule_based_task_parser.py tests/python/test_ai_safety_boundaries.py -q
```

完整回归：

```bash
python -m pytest tests/python -q
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug
ctest --preset dev-gcc-debug --output-on-failure
```