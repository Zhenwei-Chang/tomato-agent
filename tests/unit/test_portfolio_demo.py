import json
import re
from pathlib import Path

import pytest

from tomato_fertigation_agent.portfolio_demo import (
    DEFAULT_FIXTURE_ROOT,
    FixtureError,
    load_index,
    load_scenario,
    render_text,
    validate_scenario,
)
from tomato_fertigation_agent.providers.credentials import resolve_deepseek_credential


def test_all_portfolio_fixtures_validate_and_are_recorded_replays():
    index = load_index()
    assert len(index["scenarios"]) >= 4
    for entry in index["scenarios"]:
        payload = load_scenario(entry["id"])
        assert payload["execution_mode"] == "recorded_replay"
        assert payload["source"]["benchmark"].startswith("V1.4.4")
        for call in payload["tool_calls"]:
            assert call["dispatch_source"] in {
                "MODEL_GENERATED_TOOL_CALL",
                "WORKFLOW_DISPATCHED_TOOL",
                "DETERMINISTIC_FALLBACK",
                "NOT_RECORDED",
            }
            assert call["latency_ms"] == "NOT_RECORDED" or call["latency_ms"] >= 0


def test_default_fixture_root_contains_index():
    assert (DEFAULT_FIXTURE_ROOT / "index.json").is_file()


def test_comprehensive_fixture_preserves_real_six_tool_sequence():
    payload = load_scenario("comprehensive")
    assert [call["name"] for call in payload["tool_calls"]] == [
        "get_growth_context",
        "get_sensor_history",
        "predict_height_t7",
        "find_similar_cases",
        "retrieve_water_fertilizer_knowledge",
        "assess_prediction_reliability",
    ]
    assert payload["outcome"]["status"] == "PARTIAL"
    assert payload["trace"]["actual_tool_executions"] == 6
    assert {call["dispatch_source"] for call in payload["tool_calls"]} == {
        "MODEL_GENERATED_TOOL_CALL"
    }


def test_portfolio_fixtures_contain_no_local_paths_or_large_vectors():
    for entry in load_index()["scenarios"]:
        text = (DEFAULT_FIXTURE_ROOT / entry["file"]).read_text(encoding="utf-8")
        assert re.search(r"\b[A-Za-z]:[\\/]", text) is None
        payload = json.loads(text)
        for value in _walk(payload):
            assert not (isinstance(value, list) and len(value) >= 128)


def test_text_renderer_discloses_replay_mode():
    text = render_text(load_scenario("growth_prediction"))
    assert "RECORDED_REPLAY" in text
    assert "Tool calls:" in text
    assert "42.75" in text


def test_validator_rejects_live_label():
    payload = load_scenario("safety_refusal")
    payload["execution_mode"] = "live_agent"
    with pytest.raises(FixtureError, match="recorded_replay"):
        validate_scenario(payload)


def _walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def test_static_demo_assets_exist():
    root = Path(__file__).resolve().parents[2] / "demo"
    assert (root / "app.py").is_file()
    assert (root / "index.html").is_file()
    assert (root / "app.js").is_file()
    assert (root / "styles.css").is_file()
    assert (root / "favicon.svg").is_file()
    assert (root / ".nojekyll").is_file()


def test_static_demo_exposes_portfolio_interactions_and_truthfulness_labels():
    root = Path(__file__).resolve().parents[2]
    html = (root / "demo" / "index.html").read_text(encoding="utf-8")
    javascript = (root / "demo" / "app.js").read_text(encoding="utf-8")
    assert "RECORDED REPLAY · OFFLINE" in html
    assert "10 条已知开发案例" in html
    assert "48-case Holdout 仍为" in html
    for required_id in (
        'id="scenario-tabs"', 'id="copy-query"', 'id="copy-trace"',
        'id="tools"', 'id="evidence"', 'id="benchmark"',
    ):
        assert required_id in html
    assert "highlightEvidence" in javascript
    assert "dispatch_source" in javascript
    assert "NOT_RECORDED" in javascript


def test_pages_workflow_publishes_only_demo_directory():
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "path: demo" in workflow
    assert "pages: write" in workflow
    assert "id-token: write" in workflow
    assert "pull_request_target" not in workflow


def test_controlled_credential_source_does_not_expose_local_path(tmp_path):
    credential = tmp_path / "provider.env"
    credential.write_text("DEEPSEEK_API_KEY=demo-key\n", encoding="utf-8")
    resolved = resolve_deepseek_credential(credential_file=credential, env={})
    assert resolved.source == "controlled_file"
    assert str(tmp_path) not in repr(resolved)
    assert "demo-key" not in repr(resolved)
