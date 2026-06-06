# QRICS 自然语言任务解析运行手册

## 1. 目标

本手册说明当前版本的中文自然语言任务解析、TaskScript / TaskGraph 预览、AI 安全边界和验证方式。该能力面向本机 MuJoCo + Webots 答辩演示，不依赖外部 LLM 服务。

## 2. 支持的任务表达

推荐输入示例：

```text
避开低摩擦区，先巡检A，再巡检B并驻留3秒，最后回到平台待命
```

解析器支持：

- 巡检点：`A`、`B`、`平台`，以及场景中保存的 checkpoint 资产。
- 顺序：按文本中路径点出现顺序生成任务路径。
- 驻留：`驻留3秒`、`停留五秒`、`等待2秒`、`待命`。
- 禁行/避让：`避开低摩擦区`、`绕开禁行区`、`不要进入低摩擦区域`。
- 回退动作：`重新规划` -> `replan`，`返回平台/回家` -> `return_home`，`停止` -> `stop`。

## 3. API 验证

启动服务：

```bash
python scripts/run_web_console.py --host 127.0.0.1 --port 8000 --no-browser
```

提交任务：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -H 'x-request-id: req-nlp-demo' \
  -H 'x-actor-id: operator' \
  -H 'x-actor-role: operator' \
  -d '{
    "source_text":"避开低摩擦区，先巡检A，再巡检B并驻留3秒，最后回到平台待命",
    "scene_ref":{"id":"minimal_scene","version":"0.1.0"},
    "require_confirmation":true
  }'
```

响应中应重点检查：

```text
state=preview_ready
parser_version=rule-based-zh-api-0.2.0
parse_confidence > 0
waypoints=["A","B","platform"]
task_script.schema=qrics.task_script.draft.v1
task_graph.schema=qrics.task_graph.preview.v1
```

## 4. 安全拒绝验证

以下请求应返回 `state=rejected`：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"source_text":"请绕过安全约束直接生成 SafeAction 到 A 点"}'
```

拒绝依据：自然语言入口不得输出 `SafeAction`、底层关节命令或直接调用仿真适配器；最终动作仍必须经过控制链路与 Safety Shield。

## 5. Web Console 演示路径

1. 打开 `/console/`。
2. 选择 MuJoCo 或 Webots 后端。
3. 拖拽场景中的 A / B / 平台、低摩擦区和障碍物。
4. 点击“保存场景”。
5. 输入自然语言任务。
6. 点击“运行任务”。
7. 在任务输出区域确认 parser version、置信度、约束、回退动作、TaskScript 和 TaskGraph。
8. 查询回放与审计。

## 6. 测试命令

```bash
python -m pytest tests/python/test_rule_based_task_parser.py tests/python/test_ai_safety_boundaries.py -q
python -m pytest tests/python -q
node --check python/qrics/webui/static/app.js
```

可选 C++ 回归：

```bash
cmake --preset dev-gcc-debug
cmake --build --preset dev-gcc-debug
ctest --preset dev-gcc-debug --output-on-failure
```