from tools import execute_tool, read_file, search_code

read_result = read_file("llm.py", 1, 5)
search_result = search_code("def ", ".")
missing_result = execute_tool("read_file", {"path": "not_exist.py"})
unknown_result = execute_tool("unknown_tool", {})
escape_result = execute_tool("read_file", {"path": "../secret.txt"})
invalid_regex_result = execute_tool("search_code", {"pattern": "["})

print("=== read_file ===")
print(read_result)

print("\n=== search_code ===")
print(search_result)

print("\n=== 文件不存在 ===")
print(missing_result)

print("\n=== 未知工具 ===")
print(unknown_result)

print("\n=== 路径越界 ===")
print(escape_result)

print("\n=== 正则错误 ===")
print(invalid_regex_result)

assert ":" in read_result
assert "def " in search_result
assert missing_result["ok"] is False
assert unknown_result["ok"] is False
assert escape_result["ok"] is False
assert invalid_regex_result["ok"] is False

print("\n所有测试通过")