import string
from pathlib import Path


_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(domain: str, name: str, **variables: object) -> str:
    path = _PROMPTS_DIR / domain / f"{name}.txt"
    template = string.Template(path.read_text(encoding="utf-8"))
    return template.substitute(**variables)
