from __future__ import annotations

import json
import sys
from pathlib import Path

from .model import parse_tracks, to_json
from .recommend import suggest_from_payload, suggest_next
from .timing import plan_from_payload

TOOLS = {
    "plan_set": "Time an ordered set: cue A/B segment lengths, transition overlaps, warnings and total runtime.",
    "suggest_next": "Rank the next tracks for a current track using bpm, Camelot key, genre and energy.",
}

SERVER_NAME = "set-planner"
SERVER_VERSION = "0.2.0"
PROTOCOL_VERSION = "2024-11-05"

# Methods other MCP clients probe during capability negotiation. Answering with a
# valid empty result keeps the server usable from any agent, not just Codex.
EMPTY_RESULTS = {
    "resources/list": {"resources": []},
    "resources/templates/list": {"resourceTemplates": []},
    "prompts/list": {"prompts": []},
    "logging/setLevel": {},
}


def _schema(name: str) -> dict:
    if name == "plan_set":
        return {
            "type": "object",
            "properties": {
                "set": {
                    "type": "object",
                    "description": "Object with a 'tracks' array and an optional 'transitions' array.",
                    "properties": {"tracks": {"type": "array"}, "transitions": {"type": "array"}},
                    "required": ["tracks"],
                },
                "input_path": {"type": "string", "description": "Read the set JSON from this file instead."},
                "default_overlap_ms": {"type": "integer", "default": 0},
            },
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": {
            "current": {"type": "object", "description": "The track that is playing now."},
            "pool": {"type": "array", "description": "Candidate tracks to rank."},
            "library_path": {"type": "string", "description": "Read the candidate pool from this JSON file instead."},
            "current_id": {"type": "string", "description": "id of the current track when using library_path."},
            "limit": {"type": "integer", "default": 5},
            "min_score": {"type": "number", "default": 0},
            "exclude_ids": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    }


def response(request_id: object, result: object = None, error: object = None) -> dict:
    value = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        value["error"] = {"code": -32000, "message": str(error)}
    else:
        value["result"] = result
    return value


def handle(message: dict) -> "dict | None":
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if method == "initialize":
        requested = params.get("protocolVersion")
        return response(
            request_id,
            {
                "protocolVersion": requested if isinstance(requested, str) and requested else PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method == "ping":
        return response(request_id, {})
    if method in EMPTY_RESULTS:
        return response(request_id, EMPTY_RESULTS[method])
    if isinstance(method, str) and method.startswith("notifications/"):
        return None
    if method == "tools/list":
        return response(
            request_id,
            {"tools": [{"name": name, "description": description, "inputSchema": _schema(name)} for name, description in TOOLS.items()]},
        )
    if method != "tools/call":
        return response(request_id, error=f"Unsupported method: {method}")
    name = params.get("name")
    arguments = params.get("arguments") or {}
    try:
        value = _run(name, arguments)
        return response(request_id, {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]})
    except Exception as exc:
        # Tool failures are reported inside the result (MCP `isError`), not as protocol errors.
        return response(request_id, {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True})


def _run(name: str, arguments: dict) -> dict:
    if name == "plan_set":
        if arguments.get("input_path"):
            payload = json.loads(Path(arguments["input_path"]).expanduser().read_text(encoding="utf-8"))
        else:
            payload = arguments.get("set")
        if not isinstance(payload, dict):
            raise ValueError("plan_set needs a 'set' object or an 'input_path'")
        return plan_from_payload(payload, default_overlap_ms=int(arguments.get("default_overlap_ms", 0)))
    if name == "suggest_next":
        limit = int(arguments.get("limit", 5))
        min_score = float(arguments.get("min_score", 0))
        if arguments.get("library_path"):
            tracks = parse_tracks(json.loads(Path(arguments["library_path"]).expanduser().read_text(encoding="utf-8")))
            current = next((track for track in tracks if track.id == arguments.get("current_id")), None)
            if current is None:
                raise ValueError(f"no track with id {arguments.get('current_id')!r} in {arguments['library_path']}")
            exclude = tuple(str(item) for item in (arguments.get("exclude_ids") or []))
            return to_json(suggest_next(current, tracks, limit=limit, exclude_ids=exclude, min_score=min_score))
        payload = {"current": arguments.get("current"), "pool": arguments.get("pool"), "exclude_ids": arguments.get("exclude_ids")}
        return suggest_from_payload(payload, limit=limit, min_score=min_score)
    raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            result = handle(json.loads(line))
            if result is not None:
                print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps(response(None, error=exc), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
