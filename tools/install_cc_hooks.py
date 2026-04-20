#!/usr/bin/env python3
"""
Install Claude Code hooks into ~/.claude/settings.json so CC events
(Stop, SubagentStop, Notification, UserPromptSubmit) are POSTed to the
local voice-inbox HTTP server at http://127.0.0.1:8765/cc-event.

Usage:
    python tools/install_cc_hooks.py           # install (default endpoint)
    python tools/install_cc_hooks.py --port 9000
    python tools/install_cc_hooks.py --remove  # uninstall
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

MARKER = "voice-inbox cc-event"
EVENTS = ["Stop", "SubagentStop", "Notification", "UserPromptSubmit"]


def build_command(endpoint: str) -> str:
    # Pipe CC hook JSON (stdin) to voice-inbox. exit 0 so CC never breaks.
    return (
        f"cat | curl -sS -X POST "
        f"-H 'content-type: application/json' "
        f"--data-binary @- '{endpoint}' -m 2 "
        f"> /dev/null 2>&1; exit 0  # {MARKER}"
    )


def load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"Error: {path} is not valid JSON: {e}")


def is_ours(hook_entry: dict) -> bool:
    for h in hook_entry.get("hooks", []):
        if h.get("type") == "command" and MARKER in (h.get("command") or ""):
            return True
    return False


def install(settings: dict, endpoint: str) -> dict:
    hooks = settings.setdefault("hooks", {})
    command = build_command(endpoint)
    for event in EVENTS:
        entries = hooks.setdefault(event, [])
        # Drop any previous voice-inbox entry (re-install updates endpoint)
        entries[:] = [e for e in entries if not is_ours(e)]
        entries.append({
            "hooks": [{"type": "command", "command": command}]
        })
    return settings


def uninstall(settings: dict) -> dict:
    hooks = settings.get("hooks", {})
    for event in EVENTS:
        entries = hooks.get(event)
        if not entries:
            continue
        entries[:] = [e for e in entries if not is_ours(e)]
        if not entries:
            hooks.pop(event, None)
    if not hooks:
        settings.pop("hooks", None)
    return settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--settings", default="~/.claude/settings.json")
    parser.add_argument("--remove", action="store_true", help="Uninstall hooks")
    args = parser.parse_args()

    path = Path(args.settings).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    settings = load_settings(path)

    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        print(f"Backup: {backup}")

    if args.remove:
        settings = uninstall(settings)
        print(f"Removed voice-inbox hooks from {path}")
    else:
        endpoint = f"http://{args.host}:{args.port}/cc-event"
        settings = install(settings, endpoint)
        print(f"Installed hooks → {endpoint}")
        print(f"Events: {', '.join(EVENTS)}")

    path.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
