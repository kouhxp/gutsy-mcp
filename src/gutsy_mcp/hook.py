"""Claude Code PreToolUse hook: ask gutsy about risky Bash commands.

It can only add friction (ask, optionally deny), never auto-approve: a "proceed" verdict
falls through to Claude Code's normal permission rules.
"""
from __future__ import annotations

import json
import os
import re
import sys

from . import core

RISKY = re.compile(
    r"\brm\s+-[a-zA-Z]*[rf]"
    r"|\bgit\s+push\b.*(--force|\s-f\b)"
    r"|\bgit\s+(reset\s+--hard|clean\s+-[a-zA-Z]*f|branch\s+-D|filter-branch|filter-repo)\b"
    r"|\b(drop|truncate)\s+(table|database|schema)\b"
    r"|\bkubectl\s+(delete|apply|scale)\b|\bhelm\s+(upgrade|uninstall)\b"
    r"|\bterraform\s+(apply|destroy)\b"
    r"|\b(npm|pnpm|yarn)\s+publish\b|\btwine\s+upload\b|\bcargo\s+publish\b"
    r"|\b(sendmail|mailx?)\b|\bchmod\s+-R\b|\bchown\s+-R\b|\bdd\s+if=|\bmkfs"
    r"|\bdeploy\b",
    re.IGNORECASE,
)
ALLOW_DENY = os.environ.get("GUTSY_HOOK_ALLOW_DENY") == "1"


def last_user_message(transcript_path: str) -> str:
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "user":
            continue
        content = (e.get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):  # skip tool_result-only entries
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if texts:
                return "\n".join(texts)
    return ""


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if event.get("tool_name") != "Bash":
        return 0
    cmd = (event.get("tool_input") or {}).get("command", "")
    if not RISKY.search(cmd):
        return 0
    try:
        r = core.gut_check(
            cmd,
            context=f"cwd: {event.get('cwd', '')}",
            user_request=last_user_message(event.get("transcript_path", "")),
            autostart=False,  # never block the agent for a model load inside a hook
        )
    except core.GutsyUnavailable as e:
        decision, reason = "ask", f"gutsy unavailable ({e}); asking instead."
    else:
        if r["recommendation"] == "proceed":
            return 0
        p = r["verdict_probabilities"]
        decision = "deny" if (r["recommendation"] == "block" and ALLOW_DENY) else "ask"
        reason = (f"gutsy says {r['recommendation']}: {r['reason']} "
                  f"(block {p.get('block', 0):.2f}, intended {r['p_intended']:.2f}, "
                  f"reversible {r['p_reversible']:.2f})")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
