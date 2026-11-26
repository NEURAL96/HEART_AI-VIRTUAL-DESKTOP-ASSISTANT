from neural_schema import PolicyEngine
from HEART_SYSTEM_PROMPT import HEART_SYSTEM_PROMPT

_policy = PolicyEngine()

def get_system_prompt() -> str:
    return f"""
{_policy.export_for_llm()}

{HEART_SYSTEM_PROMPT}
"""