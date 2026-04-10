from typing import Any

from .base import EscapeRoomEnvironment


class FileSystemPuzzle(EscapeRoomEnvironment):
    def __init__(self, config: dict[str, Any]):
        self.files = config.get("files", {})
        self.hidden_files = config.get("hidden_files", {})
        self.flag = config.get("flag", "")
        self.hints_used = 0
        self.turn_count = 0

    async def execute_tool(self, tool_name: str, kwargs: dict[str, Any]) -> str:
        self.turn_count += 1

        if tool_name == "fs_read":
            filepath = kwargs.get("path", "")
            if filepath in self.files:
                return self.files[filepath]
            if filepath in self.hidden_files:
                return self.hidden_files[filepath]
            return f"File not found: {filepath}"

        elif tool_name == "fs_list":
            path = kwargs.get("path", "/")
            visible = list(self.files.keys())
            revealed_hidden = [
                f
                for f in self.hidden_files.keys()
                if self.turn_count >= self._get_reveal_turn(f)
            ]
            all_files = visible + revealed_hidden
            return "\n".join(sorted(all_files))

        elif tool_name == "exec_python":
            code = kwargs.get("code", "")
            return self._execute_safe_python(code)

        elif tool_name == "submit_flag":
            flag = kwargs.get("flag", "")
            if self.verify_flag(flag):
                return "FLAG ACCEPTED! Challenge complete!"
            return "Incorrect flag. Try again."

        elif tool_name == "get_hint":
            return self._get_hint()

        return f"Unknown tool: {tool_name}"

    def get_state(self) -> str:
        total = len(self.files) + len(self.hidden_files)
        return f"Filesystem with {total} files ({len(self.hidden_files)} hidden)"

    def verify_flag(self, flag: str) -> bool:
        return flag.strip() == self.flag.strip()

    def _get_reveal_turn(self, filepath: str) -> int:
        return hash(filepath) % 10 + 5

    def _get_hint(self) -> str:
        hints = {
            0: "Some files might be hidden. Keep exploring to reveal them.",
            1: "Use fs_list to see available files. Hidden files appear after more exploration.",
            2: "Check file contents carefully - the flag might be in an unexpected place.",
            3: "Tip: Hidden files often start with '.' or contain secrets.",
            4: f"There are {len(self.hidden_files)} hidden files in this challenge.",
        }
        hint = hints.get(self.hints_used, "No more hints available.")
        self.hints_used += 1
        return hint

    def _execute_safe_python(self, code: str) -> str:
        """Execute limited Python code for file analysis."""
        safe_builtins = {
            "str": str,
            "int": int,
            "len": len,
            "range": range,
            "chr": chr,
            "ord": ord,
            "print": lambda x: str(x),
        }

        try:
            result = {"output": ""}
            exec(
                code,
                {"__builtins__": safe_builtins},
                result,
            )
            return str(result.get("output", "Code executed"))
        except Exception as e:
            return f"Error: {e}"
