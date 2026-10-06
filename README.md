# Code Review Agent

一个基于大语言模型的命令行代码审查 Agent。系统按照 `输入 -> 推理 -> 工具调用 -> 观察结果 -> 最终报告` 的循环工作，支持读取文件、搜索代码、路径安全检查和 LLM 调用重试，并输出包含严重级别、文件位置、代码证据和修复建议的 Markdown 审查报告。

## 1. 功能概览

- 显式的 Agent 循环，便于观察推理、行动和观察三个阶段
- 工具集成：`read_file`、`search_code`
- 基于 Prompt 的 JSON Action 协议
- 单次会话上下文记忆，工具结果自动追加到消息历史
- LLM 调用失败自动重试，采用指数退避
- 安全边界：路径越界防护、文件大小限制、二进制文件检测、未知工具处理、最大步数限制
- 命令行交互，并输出 Agent 执行轨迹
- 工具层单元测试，覆盖正常流程和边界情况

## 2. 技术栈

| 类别 | 选择 |
|------|------|
| 语言 | Python 3.10+ |
| LLM SDK | OpenAI Python SDK（兼容 DeepSeek、通义千问、OpenAI） |
| 配置 | python-dotenv |
| 命令行 | argparse |
| 标准库 | pathlib、re、json、time |

## 3. 系统架构

```text
┌────────────────────┐
│      main.py       │  CLI 入口与结果展示
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│      agent.py      │  Agent 主循环、状态与工具调度
└─────────┬──────────┘
          │
          ├──────────────────► prompts.py
          │                    System Prompt 与输出协议
          │
          ├──────────────────► llm.py
          │                    模型客户端、重试与错误封装
          │
          └──────────────────► tools.py
                               工具注册表与执行入口
                               ├── read_file
                               └── search_code
```

## 4. 目录结构

```text
my-code-review-agent/
├── .env.example
├── .gitignore
├── README.md
├── DESIGN.md
├── requirements.txt
├── llm.py
├── tools.py
├── prompts.py
├── agent.py
├── main.py
├── hello_llm.py
├── test_tools.py
└── examples/
    ├── buggy_code.py
    └── clean_code.py
```

| 文件 | 职责 |
|------|------|
| `main.py` | 解析命令行参数，调用 Agent，打印报告和执行轨迹 |
| `agent.py` | 维护消息历史，解析模型 JSON 动作，调度工具，生成最终结果 |
| `prompts.py` | 定义 System Prompt、工具说明、JSON 协议和报告格式 |
| `llm.py` | 读取环境变量，创建兼容 OpenAI 的客户端，封装带重试的 `chat` |
| `tools.py` | 路径安全检查、工具实现、工具注册表、统一执行入口 |
| `test_tools.py` | 工具层测试，覆盖路径越界、文件不存在、未知工具和正则错误 |
| `examples/` | 演示用问题代码和规范代码 |

## 5. 环境要求

- Python 3.10 或更高版本
- 一个 OpenAI 兼容的大模型 API Key
- 推荐模型服务商：DeepSeek、通义千问、OpenAI

如果 Python 未加入系统 `PATH`，请使用解释器的绝对路径。例如：

```powershell
& 'D:\anaconda3\python.exe' --version
```

## 6. 安装

```bash
python -m pip install -r requirements.txt
```

国内网络可使用清华镜像：

```bash
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

## 7. 配置

本项目默认采用“使用者自备 API Key”的模式。每个运行者需要申请自己的模型服务商 Key，并写入本地的 `.env` 文件。

复制 `.env.example` 为 `.env`，然后从下面三种方式中选择一种。

### 方式一：DeepSeek

```text
DEEPSEEK_API_KEY=你的DeepSeekKey
```

### 方式二：通义千问

```text
DASHSCOPE_API_KEY=你的DashScopeKey
```

### 方式三：任意 OpenAI 兼容服务

```text
OPENAI_API_KEY=你的Key
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL=gpt-4o-mini
```

也可以使用通用变量：

```text
LLM_API_KEY=你的Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

`llm.py` 会自动识别上述配置并选择对应的 Base URL 和模型名称。

## 8. 使用方法

### 8.1 审查单个文件

```bash
python main.py examples/buggy_code.py
```

### 8.2 保存审查报告

```bash
python main.py examples/buggy_code.py --output report.md
```

### 8.3 调整 Agent 最大步数

```bash
python main.py examples/buggy_code.py --max-steps 10
```

参数说明：

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `path` | 是 | 无 | 要审查的文件路径 |
| `--max-steps` | 否 | `8` | Agent 最大推理步数 |
| `--output` | 否 | 无 | 将最终报告保存到指定文件 |

## 9. 输出示例

运行时，终端会先输出工具调用轨迹：

```text
[Agent 第 1 步] 正在推理...
[工具调用] read_file {'path': 'examples/buggy_code.py', 'start': 1, 'end': 200}
[工具结果] ok=True

[Agent 第 2 步] 正在推理...
[工具调用] search_code {'pattern': 'eval|exec|password|TODO', 'path': 'examples'}
[工具结果] ok=True

[Agent 第 3 步] 正在推理...
```

随后输出最终审查报告：

```markdown
## 审查报告

### 高危

1. 硬编码密钥
   - 文件：examples/buggy_code.py
   - 行号：3
   - 证据：PASSWORD = "admin123"
   - 原因：密钥进入源码和 Git 历史后难以彻底清除。
   - 建议：改用环境变量或密钥管理服务，并轮换已泄露的密钥。

2. 任意代码执行
   - 文件：examples/buggy_code.py
   - 行号：19
   - 证据：return eval(text)
   - 原因：eval 会执行不可信输入。
   - 建议：删除 eval，改用显式解析逻辑。
```

## 10. 工具说明

| 工具 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `read_file` | `path, start, end` | 带行号的文本 | 读取项目内文本文件，支持分段读取 |
| `search_code` | `pattern, path, max_results` | `文件:行号: 内容` 列表 | 使用正则表达式搜索项目代码 |

## 11. Agent 工作流程

1. `main.py` 读取用户输入的文件路径。
2. `agent.py` 初始化消息历史，包含 System Prompt 和用户请求。
3. `llm.py` 将完整消息历史发送给模型。
4. 模型返回一个 JSON 动作，例如 `read_file`、`search_code` 或 `final`。
5. `agent.py` 校验动作并调用 `tools.execute_tool`。
6. 工具结果追加到消息历史，作为下一轮推理的观察结果。
7. 重复步骤 3 至 6，直到模型返回 `final` 或达到 `max_steps`。
8. `main.py` 打印最终报告和完整工具调用轨迹。

## 12. 错误处理与安全边界

| 场景 | 处理方式 |
|------|----------|
| LLM 请求失败 | 最多重试 3 次，指数退避 |
| 模型输出非 JSON | 将错误反馈给模型，要求重新输出 |
| 模型返回未知动作 | 提示模型只能使用已注册动作 |
| 工具不存在 | 返回 `{"ok": false, "error": "未知工具"}` |
| 文件不存在 | 返回结构化错误，不中断进程 |
| 路径越界 | 拒绝访问项目根目录之外的路径 |
| 文件过大 | 拒绝整文件读取，建议分段 |
| 二进制文件 | 检测空字节并拒绝按文本读取 |
| Agent 死循环 | `max_steps` 限制最大推理步数 |

## 13. 测试

工具层测试：

```bash
python test_tools.py
```

测试覆盖：

- 正常读取文件并返回行号
- 正常搜索函数定义
- 文件不存在
- 未知工具
- 路径越界
- 非法正则表达式

完整流程演示：

```bash
python main.py examples/buggy_code.py
python main.py examples/clean_code.py
```

## 14. 设计说明

### 14.1 为什么使用 JSON Action 而不是函数调用

本项目采用显式 JSON Action 协议，而不是 OpenAI Function Calling：

- 协议透明，便于观察和调试 Agent 的每一步决策。
- 对模型服务商限制更少，兼容性更好。
- 便于在 `agent.py` 中集中处理校验、错误恢复和最大步数。

函数调用接口可以作为后续扩展，与现有工具注册表共用工具实现。

### 14.2 上下文记忆

`agent.py` 中的 `messages` 列表即单次会话的上下文记忆。每轮工具调用后，模型输出和工具结果都会追加到该列表。下一轮请求携带完整历史，因此模型能够基于此前读取的代码继续推理。

### 14.3 安全设计

所有文件访问都通过 `safe_path` 进行路径规范化与边界校验；工具执行统一经过 `execute_tool`，异常不会直接终止 Agent；仅执行受控的文件读取和正则搜索，不执行用户代码。

## 16. 已知限制

- 当前仅支持文本文件，不解析二进制或富文本格式。
- 审查质量受所选模型能力影响。
- 无自动修改代码功能。
- 会话记忆仅存在于单次进程内，未持久化。

## 17. 后续扩展

- 增加 `run_tests`、`run_linter` 工具
- 支持多文件批量审查
- 增加 Web 界面
- 持久化会话历史和审查报告
- 接入 OpenAI Function Calling
- 增加自动修复建议与差异生成
