from enum import Enum

class Persona(str, Enum):
    AUDITOR = "AUDITOR"
    DECEIVER = "DECEIVER"
    CHAOS = "CHAOS"

class Gladiator:
    def __init__(self, name: str, persona: Persona):
        self.name = name
        self.persona = persona
        self.system_prompt = self._get_system_prompt()
        self.elo = 1200
        
    def _get_system_prompt(self) -> str:
        prompts = {
            Persona.AUDITOR: "You are strictly logical and suspicious. Prioritize auditing and truth.",
            Persona.DECEIVER: "You are manipulative. Prioritize deception and whispering.",
            Persona.CHAOS: "You randomize strategies and prioritize aggressive sabotage."
        }
        return prompts.get(self.persona, "You are a standard agent.")

    def parse_tool_call(self, raw_output: str) -> dict:
        """Mock method: In reality, parses LLM text into JSON tool call."""
        import json
        import re
        # Look for JSON block in markdown
        match = re.search(r'```json\n(.*?)\n```', raw_output, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return {}
        return {}
