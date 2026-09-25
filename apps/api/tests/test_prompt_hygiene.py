"""Guard: prompt text lives in prompt modules, not in business files.

Business code must reference prompt constants/functions from a prompts module
(``prompts.py`` / ``*_prompts.py`` / platform AI capability internals); a new
inline system-prompt string inside a business file fails this test. Move the
text into the owning domain's prompts module and import it instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "realmock"

# Total literal text length inside one "content" expression that counts as a
# prompt (the transport self-test line in llm_client_ext stays under this).
MIN_PROMPT_CHARS = 80

# Files allowed to carry inline prompt text: dedicated prompt modules and the
# platform AI capability layer (the engine's own generic fragments).
def _is_allowed(path: Path) -> bool:
    rel = path.relative_to(SRC_ROOT).as_posix()
    if "platform/capabilities/ai" in rel:
        return True
    name = path.name
    return name == "prompts.py" or name.endswith("_prompts.py") or name == "hints.py"


def _literal_text_length(node: ast.AST) -> int:
    """Sum of string-literal characters embedded in an expression tree.

    Covers plain constants, f-strings, and literal concatenations so a long
    prompt cannot dodge the guard by splitting into pieces. Also drills into
    call arguments (join / get defaults) and %-format / repetition templates.
    References to names contribute nothing.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return len(node.value)
    if isinstance(node, ast.JoinedStr):
        return sum(_literal_text_length(v) for v in node.values)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, (ast.Add, ast.Mod, ast.Mult)):
            return _literal_text_length(node.left) + (
                _literal_text_length(node.right)
                if isinstance(node.op, ast.Add)
                else 0
            )
        return 0
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return sum(_literal_text_length(v) for v in node.elts)
    if isinstance(node, ast.IfExp):
        return max(_literal_text_length(node.body), _literal_text_length(node.orelse))
    if isinstance(node, ast.Call):
        total = sum(_literal_text_length(a) for a in node.args)
        total += sum(_literal_text_length(kw.value) for kw in node.keywords)
        return total
    return 0


def _system_message_violations(tree: ast.AST) -> list[tuple[int, str]]:
    """(line, sample) for dict literals shaped like {"role": "system", "content": ...}.

    Dicts containing ``**`` unpacking are matched key-by-key instead of being
    skipped, so ``{**base, "role": "system", "content": <long literal>}`` is
    still caught.
    """
    found: list[tuple[int, str]] = []

    def _const_key(k: ast.AST | None) -> str | None:
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            return str(k.value)
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        kv: dict[str, ast.AST] = {}
        for k, v in zip(node.keys, node.values):
            key = _const_key(k)
            if key is not None:
                kv[key] = v
        role = kv.get("role")
        if not (isinstance(role, ast.Constant) and role.value == "system"):
            continue
        content = kv.get("content")
        if content is None:
            continue
        length = _literal_text_length(content)
        if length >= MIN_PROMPT_CHARS:
            sample = ast.literal_eval(content) if isinstance(content, ast.Constant) else "<composed>"
            found.append((node.lineno, str(sample)[:60]))
    return found


def test_no_inline_system_prompts_outside_prompt_modules() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if _is_allowed(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, sample in _system_message_violations(tree):
            rel = path.relative_to(SRC_ROOT).as_posix()
            violations.append(f"{rel}:{lineno} {MIN_PROMPT_CHARS}+ char inline system prompt: {sample}")
    assert not violations, (
        "Prompt text must live in a prompts module, not inline in business files:\n"
        + "\n".join(violations)
    )
