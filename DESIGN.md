# Design Document: Code Review Agent

## 1. 概述

Code Review Agent 是一个命令行智能体，用于自动审查源代码并生成结构化报告。系统以 LLM 为推理核心，以工具为行动接口，通过显式的 Agent 循环完成 `输入 -> 推理 -> 工具调用 -> 观察 -> 输出` 的完整过程。

## 2. 设计目标

### 2.1 目标

- 实现可运行的 Agent 循环，而不是单次 LLM 问答。
- 支持受控工具调用，至少包含文件读取和代码搜索。
- 提供 CLI 与 Web 双交互入口，满足课程交付要求。
- 支持上下文记忆、错误处理和重试机制。
- 保持模块边界清晰，便于测试、扩展和演示。

### 2.2 非目标

- 不实现自动修改或提交代码。
- 不执行用户代码或任意 Shell 命令。
- 不构建生产级多租户服务。
- 不追求覆盖所有编程语言的语法分析。

## 3. 需求映射

| 课程要求 | 设计实现 |
|----------|----------|
| 基本 Agent 循环 | `agent.py` 中的多步推理与工具调度循环 |
| 至少一种工具 | `read_file`、`search_code` |
| 交互方式 | CLI（`main.py`）与 Web（`web.py`）双入口 |
| 上下文记忆 | `messages` 保存模型输出与工具观察结果 |
| 错误处理与重试 | LLM 重试、工具错误封装、非法动作恢复 |
| Prompt 设计 | `prompts.py` 定义系统提示词与 JSON 协议 |

## 4. 总体架构

```text
┌───────────────┐   ┌───────────────────────┐
│    main.py    │   │        web.py         │
│ CLI 解析、调用 │   │ Flask 路由、上传、SSE  │
│ Agent、展示结果│   │ 流式推送               │
└───────┬───────┘   └───────────┬───────────┘
        │                       │
        └───────────┬───────────┘
                    ▼
        ┌────────────────────────┐
        │         agent.py       │
        │ 会话状态、动作解析、      │
        │ 工具调度循环             │
        └─────┬──────────┬───────┘
              │          │
              │          └───────────────────┐
              ▼                              ▼
      ┌──────────────┐               ┌──────────────┐
      │  prompts.py  │               │    llm.py    │
      │ 系统提示词与  │               │ 模型调用、重试 │
      │ 输出协议      │               └──────────────┘
      └──────┬───────┘
             │
             ▼
      ┌────────────────────────┐
      │         tools.py       │
      │ 工具注册表、执行入口、    │
      │ 安全边界                │
      │  ├── read_file         │
      │  └── search_code       │
      └────────────────────────┘
```

## 5. 模块设计

### 5.1 `main.py`

职责：

- 解析命令行参数：目标路径、最大步数、输出文件。
- 调用 `run_agent` 启动一次审查会话。
- 打印最终报告。
- 打印工具调用轨迹，用于验证 Agent 行为。
- 捕获顶层异常并给出可读错误。

### 5.2 `agent.py`

职责：

- 初始化 `messages`，写入 System Prompt 和用户请求。
- 循环调用模型，直到获得最终报告或达到步数上限。
- 解析并校验模型返回的 JSON 动作。
- 调用 `execute_tool` 执行工具。
- 将模型输出和工具结果追加到 `messages`，形成上下文记忆。
- 维护 `trace`，记录每一步的工具名、参数和执行状态。

关键状态：

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "请审查文件：examples/buggy_code.py"},
]

trace = [
    {"step": 1, "tool": "read_file", "arguments": {...}, "ok": True},
]
```

### 5.3 `prompts.py`

System Prompt 明确定义以下契约：

- 角色：代码审查 Agent。
- 可用工具及其参数。
- 每轮只能输出一个 JSON 对象。
- 工具动作与最终动作的格式。
- 审查工作流和报告结构。
- 严重级别分组：高危、中危、低危。

### 5.4 `llm.py`

职责：

- 从 `.env` 加载 API Key、Base URL 和模型名。
- 创建 OpenAI 兼容客户端。
- 封装 `chat(messages)`。
- 对可重试异常执行最多 3 次调用，并使用指数退避。

### 5.5 `tools.py`

职责：

- 提供 `safe_path` 路径安全函数。
- 实现 `read_file`。
- 实现 `search_code`。
- 提供 `TOOLS` 注册表。
- 提供 `execute_tool` 统一执行入口。

### 5.6 `web.py`

职责：

- 提供 `GET /` 首页。
- 提供 `POST /upload` 文件上传：校验大小与二进制内容，UUID 重命名后存入 `uploads/`。
- 提供 `POST /review` 审查入口：后台线程运行 `run_agent`，`on_event` 事件经 `queue` 转为 SSE 实时推送浏览器；15 秒无事件时发送心跳注释。

## 6. LLM 交互协议

### 6.1 动作协议

模型每次只返回一个 JSON 对象。

调用工具：

```json
{
  "action": "read_file",
  "arguments": {
    "path": "examples/buggy_code.py",
    "start": 1,
    "end": 200
  }
}
```

最终回答：

```json
{
  "action": "final",
  "answer": "Markdown 格式的审查报告"
}
```

### 6.2 解析与容错

`extract_json` 的处理策略：

1. 去除首尾空白。
2. 去除可能存在的 Markdown 代码围栏。
3. 截取第一个 `{` 到最后一个 `}` 之间的内容。
4. 使用 `json.loads` 解析。
5. 解析失败时，将错误信息追加到消息历史，要求模型重新输出。

### 6.3 动作校验

允许的动作集合：

```python
ALLOWED_ACTIONS = {"read_file", "search_code", "final"}
```

未知动作不会导致进程退出，而是作为反馈写回模型，触发下一轮纠正。

## 7. 工具系统设计

### 7.1 工具注册表

```python
TOOLS = {
    "read_file": read_file,
    "search_code": search_code,
}
```

注册表将模型可调用的动作名映射到实际 Python 函数，便于扩展新工具。

### 7.2 统一执行入口

```python
def execute_tool(name: str, arguments: dict) -> dict:
    if name not in TOOLS:
        return {"ok": False, "error": f"未知工具：{name}"}
    try:
        result = TOOLS[name](**arguments)
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
```

该设计保证工具异常被转换为观察结果，而不是中断整个 Agent。

### 7.3 `read_file`

输入参数：

- `path`：项目内相对路径。
- `start`：起始行，默认 1。
- `end`：结束行，默认文件末尾。

处理流程：

1. 通过 `safe_path` 校验路径。
2. 校验存在性、文件类型和大小。
3. 检测二进制文件。
4. 解码文本并按行切片。
5. 返回 `行号: 内容` 格式文本。

### 7.4 `search_code`

输入参数：

- `pattern`：正则表达式。
- `path`：文件或目录，默认当前项目根目录。
- `max_results`：最大返回条数，默认 50。

处理流程：

1. 编译并校验正则表达式。
2. 解析目标路径。
3. 遍历文件，跳过缓存目录、二进制文件和大文件。
4. 返回 `文件:行号: 内容` 列表。

## 8. 记忆模型

系统使用消息历史作为短期记忆：

```text
system    -> 固定角色、工具和输出协议
user      -> 当前审查任务
assistant -> 模型返回的 JSON 动作
user      -> 工具执行结果（观察）
assistant -> 下一步动作
...
```

每次工具调用的结果都会进入下一轮上下文，因此模型可以基于已读取的内容继续判断。该记忆的生命周期与单次进程一致，不跨会话持久化。

## 9. 错误处理与重试

| 层级 | 错误类型 | 处理策略 |
|------|----------|----------|
| LLM | 网络错误、限流、超时 | 最多重试 3 次，指数退避 |
| 输出解析 | 非 JSON、空内容 | 反馈错误并请求重新输出 |
| 动作校验 | 未知动作、参数类型错误 | 通过统一入口返回错误观察结果 |
| 工具 | 文件不存在、路径越界、正则错误 | 返回 `ok=False`，不抛出到主循环 |
| 循环控制 | 多步无进展、模型不收敛 | `max_steps` 强制终止 |
| Web | 上传过大 / 二进制 / 空路径 | 入口校验并返回 400 与错误信息 |
| Web | SSE 长时间无事件 | 每 15 秒发送心跳注释防超时 |
| Web | 模型异常终止 | `done` 事件携带错误信息，页面显示失败提示 |

## 10. 安全性设计

- 路径隔离：所有文件访问必须位于项目根目录内。
- 输入限制：限制文件大小，避免上下文溢出。
- 类型限制：检测二进制内容，拒绝按文本读取。
- 命令执行：不执行用户代码，不调用任意 Shell 命令。
- 密钥管理：通过 `.env` 注入，不写入源码，不提交仓库。
- 上传隔离：上传文件以 UUID 重命名存入 `uploads/`，原始文件名不参与路径拼接。

## 11. 测试策略

### 11.1 工具层测试

`test_tools.py` 基于标准库 `unittest`，覆盖：

- `read_file` 正常读取与行号格式。
- `search_code` 正常匹配。
- 文件不存在。
- 未知工具。
- 路径越界（相对路径与绝对路径）。
- 非法正则表达式。
- 空文件。
- 二进制文件。
- 目录被当作文件读取。
- 缺少必填参数。

### 11.2 端到端测试

- `examples/buggy_code.py`：验证多工具调用、问题识别和报告生成。
- `examples/clean_code.py`：验证无问题或低风险场景。

### 11.3 验收命令

```bash
python test_tools.py
python main.py examples/buggy_code.py
python main.py examples/clean_code.py
python web.py    # 浏览器打开 http://127.0.0.1:5000
```

## 12. 边界情况

| 情况 | 预期行为 |
|------|----------|
| 空文件 | 返回 `(空文件)` |
| 文件不存在 | 返回结构化错误 |
| 路径越界 | 拒绝访问 |
| 文件过大 | 拒绝读取，提示分段 |
| 二进制文件 | 拒绝按文本读取 |
| `start` 超过总行数 | 返回越界提示 |
| 正则非法 | 返回错误信息 |
| 模型输出非 JSON | 触发纠正轮次 |
| 模型持续调用工具 | 达到 `max_steps` 后停止 |
| 上传文件为空 / 超 1MB / 二进制 | 入口拒绝并返回错误 |
| 请求路径为空 | 返回 400 |

## 13. 局限与后续工作

当前限制：

- 仅支持文本文件审查。
- 审查质量依赖模型能力。
- 无自动修复和自动提交。
- 无跨会话持久化记忆。

后续工作：

- 增加 `run_linter`、`run_tests` 工具。
- 支持多文件与目录级审查。
- 接入 OpenAI Function Calling。
- 持久化审查历史与报告。
- 生成结构化补丁和修复建议。
- 上传文件定期清理与生产级部署。

## 附录 A：System Prompt 摘要

```text
角色：代码审查 Agent
工具：read_file、search_code
协议：每轮仅输出一个 JSON 对象
动作：read_file / search_code / final
流程：读取 -> 搜索 -> 汇总 -> 输出报告
报告：严重级别、文件、行号、证据、原因、修复建议
```

## 附录 B：消息流转示例

```text
Step 1
assistant -> {"action": "read_file", "arguments": {"path": "examples/buggy_code.py"}}
user      -> {"ok": true, "result": "1: import os\n2: ..."}

Step 2
assistant -> {"action": "search_code", "arguments": {"pattern": "eval|password", "path": "examples"}}
user      -> {"ok": true, "result": "examples/buggy_code.py:3: PASSWORD = ..."}

Step 3
assistant -> {"action": "final", "answer": "## 审查报告 ..."}
```
