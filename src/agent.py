import json
import os
import subprocess
import time
import requests

URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
API_KEY = os.environ.get("GROQ_API_KEY", "")

MAX_READ_BYTES = 100_000
MAX_OUTPUT_CHARS = 10_000

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "system_prompt.txt")
with open(PROMPT_PATH) as f:
    SYSTEM_PROMPT = f.read()


def read_file(path):
    if not os.path.isfile(path):
        return f"Error: '{path}' is not a readable file."
    size = os.path.getsize(path)
    if size > MAX_READ_BYTES:
        return f"Error: '{path}' is {size} bytes; too large to read (limit {MAX_READ_BYTES})."
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    return "".join(f"{i}\t{line}" for i, line in enumerate(lines, 1))


def list_dir(path="."):
    if not os.path.isdir(path):
        return f"Error: '{path}' is not a directory."
    names = sorted(os.listdir(path))
    if not names:
        return "(empty)"
    return "\n".join(
        n + "/" if os.path.isdir(os.path.join(path, n)) else n for n in names
    )


def write_file(path, content):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote {len(content)} characters to '{path}'."


def run_shell(command):
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 30s."
    output = result.stdout + result.stderr
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + f"\n... (truncated, {len(output)} chars total)"
    return output if output.strip() else f"(exit {result.returncode}, no output)"


TOOL_LIST = [
    {
        "fn": read_file,
        "schema": {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": (
                    "Read a UTF-8 text file and return its contents with line numbers "
                    "(each line prefixed by its line number and a tab). Fails for a "
                    "missing/non-file path or a file larger than ~100 KB."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to the file to read."}
                    },
                    "required": ["path"],
                },
            },
        },
    },
    {
        "fn": list_dir,
        "schema": {
            "type": "function",
            "function": {
                "name": "list_dir",
                "description": (
                    "List the entries in a directory, sorted, with subdirectories marked "
                    "by a trailing '/'. Defaults to the current directory."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path. Defaults to the current directory.",
                        }
                    },
                    "required": [],
                },
            },
        },
    },
    {
        "fn": write_file,
        "confirm": True,
        "schema": {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": (
                    "Create or overwrite a file with the given text content, replacing "
                    "the entire file. Creates parent directories if needed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to the file to write."},
                        "content": {"type": "string", "description": "The full text to write into the file."},
                    },
                    "required": ["path", "content"],
                },
            },
        },
    },
    {
        "fn": run_shell,
        "confirm": True,
        "schema": {
            "type": "function",
            "function": {
                "name": "run_shell",
                "description": (
                    "Run a shell command and return its combined stdout and stderr. "
                    "Times out after 30s; very long output is truncated."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The shell command to run."}
                    },
                    "required": ["command"],
                },
            },
        },
    },
]

TOOLS = {t["schema"]["function"]["name"]: t["fn"] for t in TOOL_LIST}
TOOL_SCHEMAS = [t["schema"] for t in TOOL_LIST]
NEEDS_APPROVAL = {t["schema"]["function"]["name"] for t in TOOL_LIST if t.get("confirm")}


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ModelError(Exception):
    pass


def call_model(messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                URL,
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={"model": MODEL, "messages": messages, "tools": TOOL_SCHEMAS},
                timeout=60,
            )
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                print(f"  [network error, retrying in {2 ** attempt}s...]")
                time.sleep(2 ** attempt)
                continue
            raise ModelError(f"network error after {max_retries} attempts: {e}")

        if resp.status_code == 200:
            data = resp.json()
            if "choices" in data:
                return data["choices"][0]
            raise ModelError(f"unexpected response: {data}")

        if resp.status_code in RETRYABLE_STATUS and attempt < max_retries - 1:
            print(f"  [HTTP {resp.status_code}, retrying in {2 ** attempt}s...]")
            time.sleep(2 ** attempt)
            continue

        raise ModelError(f"API error {resp.status_code}: {resp.text[:300]}")


def approved(name, args):
    answer = input(f"  approve {name}({args})? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def run_one_tool(name, args):
    if name not in TOOLS:
        return f"Error: unknown tool '{name}'."
    if name in NEEDS_APPROVAL and not approved(name, args):
        return "User denied this action."
    try:
        return TOOLS[name](**args)
    except Exception as e:
        return f"Error: {name} failed: {e}"


def execute_tool_calls(tool_calls):
    results = []
    for tc in tool_calls:
        name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {}
        print(f"[tool] {name}({args})")
        content = run_one_tool(name, args)
        results.append({"role": "tool", "tool_call_id": tc["id"], "content": content})
    return results


def main():
    if not API_KEY:
        raise SystemExit("Set GROQ_API_KEY (free key at https://console.groq.com).")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input("you> ")
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not user_input.strip():
            continue

        messages.append({"role": "user", "content": user_input})

        while True:
            try:
                choice = call_model(messages)
            except ModelError as e:
                print("bot> [error]", e)
                break

            msg = choice["message"]
            messages.append(msg)

            if choice["finish_reason"] == "tool_calls":
                messages.extend(execute_tool_calls(msg["tool_calls"]))
                continue

            print("bot>", msg["content"])
            break


if __name__ == "__main__":
    main()
