"""Dependency-light viewer for curated, recorded portfolio scenarios.

This module never constructs the real ToolRegistry and never calls an LLM. It
only reads sanitized fixtures committed under ``demo/fixtures``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _default_fixture_root() -> Path:
    """Resolve fixtures from a source checkout or an installed wheel."""
    candidates = (
        PROJECT_ROOT / "demo" / "fixtures",
        Path(sys.prefix) / "share" / "tomato-agent" / "demo" / "fixtures",
    )
    return next((path for path in candidates if (path / "index.json").is_file()), candidates[0])


DEFAULT_FIXTURE_ROOT = _default_fixture_root()
LOCAL_DRIVE_PATH = re.compile(r"\b[A-Za-z]:[\\/]")


class FixtureError(RuntimeError):
    """Raised when a replay fixture is missing or violates the demo contract."""


def load_index(root: Path = DEFAULT_FIXTURE_ROOT) -> dict[str, Any]:
    path = root / "index.json"
    if not path.is_file():
        raise FixtureError(f"Fixture index not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0":
        raise FixtureError("Unsupported fixture index schema")
    return payload


def load_scenario(scenario_id: str, root: Path = DEFAULT_FIXTURE_ROOT) -> dict[str, Any]:
    index = load_index(root)
    entry = next((x for x in index.get("scenarios", []) if x.get("id") == scenario_id), None)
    if entry is None:
        raise FixtureError(f"Unknown scenario: {scenario_id}")
    path = root / entry["file"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_scenario(payload)
    return payload


def validate_scenario(payload: dict[str, Any]) -> None:
    required = {"schema_version", "scenario_id", "execution_mode", "query", "outcome", "tool_calls", "evidence"}
    missing = sorted(required - payload.keys())
    if missing:
        raise FixtureError(f"Scenario missing fields: {', '.join(missing)}")
    if payload["schema_version"] != "1.0":
        raise FixtureError("Unsupported scenario schema")
    if payload["execution_mode"] != "recorded_replay":
        raise FixtureError("Portfolio fixtures must be labelled recorded_replay")
    evidence_ids = [item.get("id") for item in payload["evidence"]]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise FixtureError("Evidence IDs must be unique within a scenario")
    allowed_sources = {
        "MODEL_GENERATED_TOOL_CALL",
        "WORKFLOW_DISPATCHED_TOOL",
        "DETERMINISTIC_FALLBACK",
        "NOT_RECORDED",
    }
    for call in payload["tool_calls"]:
        if call.get("dispatch_source") not in allowed_sources:
            raise FixtureError("Tool dispatch_source is missing or unsupported")
        latency = call.get("latency_ms")
        if latency != "NOT_RECORDED" and not (
            isinstance(latency, (int, float)) and not isinstance(latency, bool) and latency >= 0
        ):
            raise FixtureError("Tool latency_ms must be recorded numeric data or NOT_RECORDED")
    for claim in payload.get("claims", []):
        unknown = sorted(set(claim.get("support", [])) - set(evidence_ids))
        if unknown:
            raise FixtureError(f"Claim references unknown evidence IDs: {', '.join(unknown)}")
    serialized = json.dumps(payload, ensure_ascii=False)
    if LOCAL_DRIVE_PATH.search(serialized):
        raise FixtureError("Fixture contains a local Windows path")
    if "512D" in serialized and "embedding" in serialized.lower():
        # Describing an embedding dimension is fine; arrays are not.
        arrays = [v for v in _walk(payload) if isinstance(v, list) and len(v) >= 128 and all(isinstance(n, (int, float)) for n in v)]
        if arrays:
            raise FixtureError("Fixture contains a large numerical vector")


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def render_text(payload: dict[str, Any]) -> str:
    outcome = payload["outcome"]
    lines = [
        f"[{payload['execution_mode'].upper()}] {payload['title']}",
        f"Scenario: {payload['scenario_id']}",
        f"Query: {payload['query']}",
        f"Status: {outcome['status']} | Reliability: {outcome.get('reliability', 'UNKNOWN')}",
        f"Answer: {outcome['summary']}",
        "",
        "Tool calls:",
    ]
    if payload["tool_calls"]:
        for call in payload["tool_calls"]:
            suffix = f" ({call['error_code']})" if call.get("error_code") else ""
            lines.append(f"  {call['index']}. {call['name']} -> {call['status']} [{call['scope']}]{suffix}")
    else:
        lines.append("  (none; request rejected before tool execution)")
    lines.extend(["", "Evidence:"])
    if payload["evidence"]:
        for item in payload["evidence"]:
            lines.append(f"  - {item['id']}: {item['summary']} [{item['scope']}; {item['reliability']}]")
    else:
        lines.append("  (none)")
    lines.extend(["", "Disclosure: " + payload["disclosure"]])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect sanitized Tomato Agent replay fixtures")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURE_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list available scenarios")
    show = sub.add_parser("show", help="render one recorded scenario")
    show.add_argument("scenario_id")
    sub.add_parser("check", help="validate every fixture")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        for entry in load_index(args.fixtures)["scenarios"]:
            print(f"{entry['id']}: {entry['title']}")
        return 0
    if args.command == "show":
        print(render_text(load_scenario(args.scenario_id, args.fixtures)))
        return 0
    for entry in load_index(args.fixtures)["scenarios"]:
        load_scenario(entry["id"], args.fixtures)
    print("All recorded replay fixtures are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
