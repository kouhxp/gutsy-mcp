# gutsy-mcp

<!-- mcp-name: io.github.kouhxp/gutsy -->

A local **gut check** for coding agents. Before Claude Code, Codex, Cursor or Copilot runs
`rm -rf`, force-pushes, deploys or sends something, it calls `gut_check` and gets back
calibrated probabilities that the action is intended and safe, plus a recommendation:
`proceed`, `confirm` (ask the user first) or `block`.

Runs on your CPU with [gutsy](https://github.com/kouhxp/gutsy) (0.8B, 775 MB GGUF).
No API calls, no per-call cost, deterministic, and your code never leaves the machine.

## What it is and isn't

It's a fast second opinion that adds friction where it's warranted. It is **not** a
security boundary: the agent decides whether to call it and writes the context it sees,
and a 0.8B model is weak at ambiguity and multi-step rules (see the model card). Keep
your normal permission settings on. Default thresholds aren't tuned for your workflow;
log the probabilities and adjust them.

## 1. Start the gutsy runtime

```bash
git clone https://github.com/kouhxp/gutsy
pip install -e gutsy/gutsy-inference
hf download kouhxp/gutsy --include "gutsy-0.8b-v04*" --local-dir gutsy/gutsy-inference/models
cd gutsy/gutsy-inference && cp models.example.json models.json
gutsy-inference check && gutsy-inference serve     # http://127.0.0.1:8765
```

Or set `GUTSY_INFERENCE_DIR=/path/to/gutsy/gutsy-inference` and gutsy-mcp starts it on
first use.

## 2. Add the MCP server

Claude Code:

```bash
claude mcp add gutsy -- uvx gutsy-mcp
```

Cursor (`.cursor/mcp.json`) / Claude Desktop:

```json
{ "mcpServers": { "gutsy": { "command": "uvx", "args": ["gutsy-mcp"] } } }
```

VS Code (`.vscode/mcp.json`):

```json
{ "servers": { "gutsy": { "type": "stdio", "command": "uvx", "args": ["gutsy-mcp"] } } }
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.gutsy]
command = "uvx"
args = ["gutsy-mcp"]
```

Then tell the agent when to use it (`CLAUDE.md`, `AGENTS.md`, `.cursor/rules`):

> Before deleting files, rewriting git history, force-pushing, touching databases,
> deploying, publishing or sending anything, call `gut_check`. If it doesn't return
> `proceed`, stop and ask me.

## 3. Optional: enforce it with a Claude Code hook

An MCP tool only runs if the agent remembers to call it. The hook runs on every risky-looking
Bash command regardless. It can only ask or deny, never auto-approve.

```bash
uv tool install gutsy-mcp      # puts gutsy-hook on PATH
```

`.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [{ "type": "command", "command": "gutsy-hook", "timeout": 60 }] }
    ]
  }
}
```

`block` becomes a confirmation prompt by default; set `GUTSY_HOOK_ALLOW_DENY=1` to deny outright.

## Tool

`gut_check(action, context="", user_request="")` returns:

```json
{
  "recommendation": "confirm",
  "reason": "Not confident enough to proceed without the user.",
  "p_intended": 0.41,
  "p_reversible": 0.08,
  "verdict_probabilities": {"proceed": 0.22, "confirm": 0.61, "block": 0.17},
  "reject": 0.04,
  "confidence": 0.42
}
```

| env var | default | |
|---|---|---|
| `GUTSY_URL` | `http://127.0.0.1:8765` | runtime URL |
| `GUTSY_INFERENCE_DIR` | | lets gutsy-mcp start the runtime |
| `GUTSY_MODEL` | runtime default | model name from `models.json` |
| `GUTSY_PROCEED_MIN` | `0.85` | |
| `GUTSY_BLOCK_MIN` | `0.50` | |
| `GUTSY_API_KEY` | | if you run `serve --api-key-env` |

License: Apache 2.0.
