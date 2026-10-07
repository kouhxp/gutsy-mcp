"""Shared logic: build the gutsy request, call the local runtime, turn probabilities into a recommendation."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request

GUTSY_URL = os.environ.get("GUTSY_URL", "http://127.0.0.1:8765").rstrip("/")
GUTSY_MODEL = os.environ.get("GUTSY_MODEL", "")  # empty = runtime default
INFERENCE_DIR = os.environ.get("GUTSY_INFERENCE_DIR", "")  # dir with models.json, for autostart
PROCEED_MIN = float(os.environ.get("GUTSY_PROCEED_MIN", "0.85"))
BLOCK_MIN = float(os.environ.get("GUTSY_BLOCK_MIN", "0.50"))
TIMEOUT_S = float(os.environ.get("GUTSY_TIMEOUT", "60"))  # CPU p95 on long states is ~23 s
MAX_FIELD_CHARS = 4000  # keep state + questions well inside the 8,192-token context

NOTE = ("Advisory second opinion from a 0.8B local model, not a security boundary. "
        "Default thresholds are not tuned for this task.")

QUESTIONS = {
    "intended": {
        "type": "noul",
        "instructions": "Did the user ask for, or clearly agree to, the proposed action, "
                        "including its scope (which files, branch, environment or recipients)?",
    },
    "reversible": {
        "type": "noul",
        "instructions": "Could the effects of the proposed action be fully and easily undone afterwards?",
    },
    "verdict": {
        "type": "choice",
        "instructions": "What should a careful coding agent do with the proposed action?",
        "criteria": {
            "proceed": "safe and clearly what the user wants: run it",
            "confirm": "plausibly fine but risky, broad or unclear: ask the user first",
            "block": "destructive, out of scope or not what the user asked for: do not run it",
        },
    },
}


class GutsyUnavailable(RuntimeError):
    pass


def _healthy() -> bool:
    try:
        with urllib.request.urlopen(GUTSY_URL + "/health", timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


_server_proc: subprocess.Popen | None = None


def ensure_runtime(wait_s: float = 90) -> None:
    """Make sure gutsy-inference is reachable; start it if GUTSY_INFERENCE_DIR is set."""
    global _server_proc
    if _healthy():
        return
    exe = shutil.which("gutsy-inference")
    if not (INFERENCE_DIR and exe):
        raise GutsyUnavailable(
            f"No gutsy runtime at {GUTSY_URL}. Start one with `gutsy-inference serve` "
            "(https://github.com/kouhxp/gutsy), or set GUTSY_INFERENCE_DIR so gutsy-mcp can start it."
        )
    if _server_proc is None or _server_proc.poll() is not None:
        # DEVNULL matters: anything written to our stdout would corrupt the MCP stdio stream.
        _server_proc = subprocess.Popen(
            [exe, "serve"], cwd=INFERENCE_DIR,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if _healthy():
            return
        time.sleep(0.5)
    raise GutsyUnavailable("gutsy-inference was started but did not become healthy in time.")


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        GUTSY_URL + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    key = os.environ.get("GUTSY_API_KEY")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.load(r)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise GutsyUnavailable(f"gutsy request failed: {e}") from e


def _clip(s: str) -> str:
    s = (s or "").strip()
    return s if len(s) <= MAX_FIELD_CHARS else s[:MAX_FIELD_CHARS] + " ...[truncated]"


def recommend(p_intended: float, probs: dict, reject: float) -> tuple[str, str]:
    """Map probabilities to proceed / confirm / block. Fails toward 'confirm'."""
    if reject >= 0.5:
        return "confirm", "The context doesn't settle it; ask the user."
    if probs.get("block", 0.0) >= BLOCK_MIN:
        return "block", "Looks destructive, out of scope or unrequested."
    if probs.get("proceed", 0.0) >= PROCEED_MIN and p_intended >= PROCEED_MIN:
        return "proceed", "Looks safe and clearly requested."
    return "confirm", "Not confident enough to proceed without the user."


def gut_check(action: str, context: str = "", user_request: str = "", autostart: bool = True) -> dict:
    if autostart:
        ensure_runtime()
    elif not _healthy():
        raise GutsyUnavailable(f"No gutsy runtime at {GUTSY_URL}.")
    payload: dict = {
        "state": {
            "user_request": _clip(user_request) or "(not provided)",
            "context": _clip(context) or "(not provided)",
            "proposed_action": _clip(action),
        },
        "questions": QUESTIONS,
    }
    if GUTSY_MODEL:
        payload["model"] = GUTSY_MODEL
    resp = _post("/v1/systemone", payload)
    try:
        a = resp["answers"]
        p_intended = float(a["intended"]["noul"])
        p_reversible = float(a["reversible"]["noul"])
        verdict = a["verdict"]
        probs = {k: float(v) for k, v in verdict["probabilities"].items()}
        reject = float(verdict.get("reject", 0.0))
    except (KeyError, TypeError, ValueError) as e:
        raise GutsyUnavailable(f"Unexpected gutsy response: {e}") from e
    rec, reason = recommend(p_intended, probs, reject)
    return {
        "recommendation": rec,
        "reason": reason,
        "p_intended": round(p_intended, 4),
        "p_reversible": round(p_reversible, 4),
        "verdict_probabilities": {k: round(v, 4) for k, v in probs.items()},
        "reject": round(reject, 4),
        "confidence": verdict.get("confidence"),
        "model": resp.get("model"),
        "latency_ms": (resp.get("usage") or {}).get("latency_ms"),
        "note": NOTE,
    }
