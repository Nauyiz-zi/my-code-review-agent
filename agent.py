import json

from llm import chat
from prompts import SYSTEM_PROMPT
from tools import execute_tool

ALLOWED_ACTIONS = {"read_file", "search_code", "final"}


def extract_json(text: str) -> dict:
    if not isinstance(text, str):
        raise ValueError("模型返回的不是文本")

    text = text.strip()

    if "```" in text:
        text = text.replace("```json", "").replace("```", "").strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("模型没有返回 JSON 对象")

    return json.loads(text[start:end + 1])


def content_to_text(reply) -> str:
    if isinstance(reply, str):
        return reply

    content = getattr(reply, "content", None)
    if content is None:
        raise ValueError("模型返回内容为空")

    return content


def run_agent(target_path: str, max_steps: int = 8) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"请审查文件：{target_path}"},
    ]
    trace = []

    for step in range(1, max_steps + 1):
        print(f"\n[Agent 第 {step} 步] 正在推理...")
        reply = content_to_text(chat(messages))

        try:
            action = extract_json(reply)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"[解析失败] {exc}")
            messages.append({"role": "assistant", "content": reply})
            messages.append({
                "role": "user",
                "content": f"你的输出不是合法 JSON：{exc}。请只输出一个 JSON 对象。",
            })
            continue

        if not isinstance(action, dict):
            messages.append({"role": "assistant", "content": reply})
            messages.append({
                "role": "user",
                "content": "JSON 顶层必须是对象，请重新输出。",
            })
            continue

        action_name = action.get("action")

        if action_name not in ALLOWED_ACTIONS:
            messages.append({"role": "assistant", "content": reply})
            messages.append({
                "role": "user",
                "content": "action 只能是 read_file、search_code 或 final，请重新输出 JSON。",
            })
            continue

        if action_name == "final":
            answer = (
                action.get("answer")
                or action.get("content")
                or "模型没有提供最终答案。"
            )
            return {"answer": answer, "trace": trace}

        arguments = action.get("arguments", {})

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        print(f"[工具调用] {action_name} {arguments}")
        result = execute_tool(action_name, arguments)
        print(f"[工具结果] ok={result['ok']}")

        trace.append({
            "step": step,
            "tool": action_name,
            "arguments": arguments,
            "ok": result["ok"],
        })

        messages.append({"role": "assistant", "content": reply})
        messages.append({
            "role": "user",
            "content": "工具执行结果如下：\n"
                       + json.dumps(result, ensure_ascii=False, indent=2),
        })

    return {
        "answer": "达到最大步数，Agent 已停止。请检查文件，或者增大 --max-steps。",
        "trace": trace,
    }