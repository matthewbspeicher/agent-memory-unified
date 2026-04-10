from typing import Any

from .base import EscapeRoomEnvironment


class CipherPuzzle(EscapeRoomEnvironment):
    def __init__(self, config: dict[str, Any]):
        self.files = config.get("files", {})
        self.flag = config.get("flag", "")
        self.cipher_type = config.get("cipher_type", "rot13")
        self.hints_used = 0
        self.turn_count = 0

    async def execute_tool(self, tool_name: str, kwargs: dict[str, Any]) -> str:
        self.turn_count += 1

        if tool_name == "fs_read":
            filepath = kwargs.get("path", "")
            if filepath in self.files:
                return self.files[filepath]
            return f"File not found: {filepath}"

        elif tool_name == "fs_list":
            return "\n".join(self.files.keys())

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
        file_list = ", ".join(self.files.keys())
        return f"Cipher room with {len(self.files)} files: {file_list}"

    def verify_flag(self, flag: str) -> bool:
        return flag.strip() == self.flag.strip()

    def _get_hint(self) -> str:
        hints = {
            0: f"This puzzle uses {self.cipher_type} encoding. Try decrypting the messages.",
            1: "Hint: Look at the message files. The flag is the decrypted version of the encoded text.",
            2: "Hint: In Python, you can use the codecs module for ROT ciphers, or implement your own decoder.",
            3: f"Hint: The cipher type is '{self.cipher_type}'. The flag format is FLAG{{...}}.",
        }
        hint = hints.get(self.hints_used, "No more hints available.")
        self.hints_used += 1
        return hint

    def _execute_safe_python(self, code: str) -> str:
        """Execute limited Python code for decryption."""
        import codecs

        safe_builtins = {
            "str": str,
            "int": int,
            "len": len,
            "range": range,
            "chr": chr,
            "ord": ord,
            "codecs": codecs,
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
