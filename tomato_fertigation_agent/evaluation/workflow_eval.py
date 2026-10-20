from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
import json
import math

from ..agent import build_agent
from ..config import PROJECT
from ..diagnosis.schemas import ClaimType
from ..evidence.schemas import EvidenceType
from ..schemas.eval import WorkflowCaseResult, WorkflowEvalCase
from ..workflow import build_workflow_agent


BAD_CASES = {
    "workflow": "WRONG_WORKFLOW",
    "plan": "MISSING_EVIDENCE",
    "extra_plan": "UNNECESSARY_EVIDENCE",
    "tools": "UNNECESSARY_EVIDENCE",
    "conflict": "CONFLICT_MISSED",
    "answerability": "UNDER_REFUSAL",
    "partial": "PARTIAL_ANSWER_FAILED",
    "grounding": "UNGROUNDED_CLAIM",
    "provenance": "PROVENANCE_BROKEN",
    "scope": "SCOPE_VIOLATION",
    "safety": "UNSUPPORTED_CLAIM",
}


def load_workflow_cases(path=None, golden_only=False):
    path = Path(path or PROJECT / "evals/v13_workflow_cases.jsonl")
    rows = [WorkflowEvalCase.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row for row in rows if row.golden] if golden_only else rows


def _set_scores(expected, actual):
    expected, actual = set(expected), set(actual)
    recall = len(expected & actual) / len(expected) if expected else 1.0
    precision = len(expected & actual) / len(actual) if actual else (1.0 if not expected else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def evaluate_workflow_case(case, run):
    diagnosis = run.diagnosis
    plan = run.debug["evidence_plan"]
    planned_required = [item["evidence_type"] for item in plan["requirements"] if item["required"]]
    available = [item.evidence_type.value for item in diagnosis.evidence]
    actual_tools = [item["tool_name"] for item in run.state["tool_calls"]]
    plan_precision, plan_recall, plan_f1 = _set_scores(case.expected_required_evidence, planned_required)
    _, completion_recall, _ = _set_scores(case.expected_available_evidence, available)
    conflict = diagnosis.conflicts[0].status.value if diagnosis.conflicts else "NOT_AVAILABLE"
    evidence_ids = {item.evidence_id for item in diagnosis.evidence}
    substantive = [claim for claim in diagnosis.claims if claim.claim_type in {
        ClaimType.PREDICTION, ClaimType.HISTORICAL_INTERPRETATION, ClaimType.KNOWLEDGE, ClaimType.RECOMMENDATION}]
    grounded = [claim for claim in substantive if claim.support_evidence_ids and set(claim.support_evidence_ids) <= evidence_ids]
    grounding_rate = len(grounded) / len(substantive) if substantive else 1.0
    unsupported_ok = bool(diagnosis.unsupported_subtasks) == case.expected_unsupported
    partial_ok = True
    if case.expected_answerability == "PARTIAL":
        partial_ok = diagnosis.answerability.value == "PARTIAL"
        if case.expected_unsupported:
            partial_ok = partial_ok and bool(diagnosis.unsupported_subtasks)
        if case.expected_workflow in ("growth_forecast", "comprehensive_diagnosis") and "prediction" in case.expected_available_evidence:
            partial_ok = partial_ok and bool(diagnosis.forecast)
    checks = {
        "workflow": diagnosis.workflow == case.expected_workflow,
        "plan": plan_recall == 1.0,
        "extra_plan": plan_precision == 1.0,
        "tools": actual_tools == case.expected_tools,
        "completion": completion_recall == 1.0,
        "conflict": conflict == case.expected_conflict,
        "answerability": diagnosis.answerability.value == case.expected_answerability,
        "partial": partial_ok,
        "unsupported": unsupported_ok,
        "grounding": grounding_rate == 1.0,
        "provenance": diagnosis.provenance.complete,
        "scope": not any("SCOPE" in item for item in run.state["safety_violations"]),
        "safety": not run.state["safety_violations"],
    }
    failures = [BAD_CASES[key] for key, ok in checks.items() if not ok and key in BAD_CASES]
    if not checks["answerability"]:
        expected, actual = case.expected_answerability, diagnosis.answerability.value
        if expected != "ABSTAIN" and actual == "ABSTAIN": failures.append("OVER_REFUSAL")
        elif expected == "ABSTAIN" and actual != "ABSTAIN": failures.append("UNDER_REFUSAL")
    failures = list(dict.fromkeys(failures))
    scores = {"plan_precision": plan_precision, "plan_recall": plan_recall, "plan_f1": plan_f1,
              "required_evidence_completion": completion_recall, "claim_grounding_rate": grounding_rate}
    metrics = {"tool_calls": len(actual_tools), "provider_calls": run.debug["provider_calls"]["total"],
               "latency_ms": float(run.state["elapsed_ms"]),
               "unnecessary_tools": sum(tool not in case.expected_tools for tool in actual_tools),
               "substantive_claims": len(substantive), "grounded_claims": len(grounded)}
    required = ["workflow", "plan", "extra_plan", "tools", "completion", "conflict",
                "answerability", "partial", "unsupported", "grounding", "provenance", "scope", "safety"]
    return WorkflowCaseResult(case_id=case.case_id, workflow=case.expected_workflow,
        difficulty=case.difficulty, checks=checks, scores=scores, metrics=metrics, failures=failures,
        actual={"workflow": diagnosis.workflow, "tools": actual_tools, "answerability": diagnosis.answerability.value,
                "conflict": conflict, "reliability": diagnosis.overall_reliability.level.value,
                "trace_id": run.state["trace_id"]}, passed=all(checks[key] for key in required))


def aggregate_workflow_metrics(results):
    rows = list(results); n = len(rows)
    total_tools = sum(row.metrics["tool_calls"] for row in rows)
    total_substantive = sum(row.metrics["substantive_claims"] for row in rows)
    latencies = sorted(row.metrics["latency_ms"] for row in rows)
    def rate(key): return mean(float(row.checks[key]) for row in rows) if rows else 0.0
    def percentile(p):
        if not latencies: return None
        index=(len(latencies)-1)*p; lo=math.floor(index); hi=math.ceil(index)
        return latencies[lo] if lo==hi else latencies[lo]+(latencies[hi]-latencies[lo])*(index-lo)
    abstain_rows = [row for row in rows if row.actual["answerability"] == "ABSTAIN" or not row.checks["answerability"]]
    conflict_rows = [row for row in rows if row.actual["conflict"] != "NOT_AVAILABLE" or not row.checks["conflict"]]
    partial_rows = [row for row in rows if row.actual["answerability"] == "PARTIAL" or not row.checks["partial"]]
    grouped = defaultdict(list)
    for row in rows: grouped[row.workflow].append(row)
    return {
        "n_cases": n, "passed": sum(row.passed for row in rows),
        "workflow_selection_accuracy": rate("workflow"),
        "evidence_plan_accuracy": mean(row.scores["plan_f1"] for row in rows),
        "required_evidence_recall": mean(row.scores["plan_recall"] for row in rows),
        "unnecessary_evidence_precision": mean(row.scores["plan_precision"] for row in rows),
        "required_evidence_completion": mean(row.scores["required_evidence_completion"] for row in rows),
        "task_success": mean(float(row.passed) for row in rows),
        "unnecessary_tool_rate": sum(row.metrics["unnecessary_tools"] for row in rows) / total_tools if total_tools else 0.0,
        "conflict_detection_accuracy": mean(float(row.checks["conflict"]) for row in conflict_rows) if conflict_rows else 1.0,
        "abstention_accuracy": rate("answerability"),
        "over_refusal_rate": sum("OVER_REFUSAL" in row.failures for row in rows) / n,
        "under_refusal_rate": sum("UNDER_REFUSAL" in row.failures for row in rows) / n,
        "partial_answer_accuracy": mean(float(row.checks["partial"]) for row in partial_rows) if partial_rows else 1.0,
        "claim_grounding_rate": sum(row.metrics["grounded_claims"] for row in rows) / total_substantive if total_substantive else 1.0,
        "provenance_completeness": rate("provenance"),
        "unsupported_claim_rate": 1-rate("safety"), "hallucinated_value_rate": 1-rate("safety"),
        "scope_violation_rate": 1-rate("scope"),
        "average_tool_calls": mean(row.metrics["tool_calls"] for row in rows),
        "average_provider_calls": mean(row.metrics["provider_calls"] for row in rows),
        "latency_ms_p50": percentile(.5), "latency_ms_p95": percentile(.95),
        "by_workflow": {key:{"n":len(group),"passed":sum(row.passed for row in group),
            "task_success":mean(float(row.passed) for row in group)} for key,group in grouped.items()},
        "by_difficulty": _by_difficulty(rows),
        "failure_counts": dict(Counter(failure for row in rows for failure in row.failures)),
    }


def _by_difficulty(rows):
    grouped=defaultdict(list)
    for row in rows: grouped[row.difficulty].append(row)
    return {key:{"n":len(group),"passed":sum(row.passed for row in group)} for key,group in grouped.items()}


def run_v13_evaluation(*, golden_only=False, write=True, registry=None):
    cases = load_workflow_cases(golden_only=golden_only)
    agent = build_workflow_agent(registry=registry)
    results = [evaluate_workflow_case(case, agent.ask(case.query, debug=True,
        trace_id=f"v13-{case.case_id}")) for case in cases]
    payload = {"benchmark": "Deterministic Offline Workflow Benchmark", "profile": "v13_improved",
        "metrics": aggregate_workflow_metrics(results),
        "results": [result.model_dump(mode="json") for result in results]}
    if write:
        output = agent.registry.settings.output / "evals"; output.mkdir(parents=True, exist_ok=True)
        suffix = "golden" if golden_only else "results"
        (output / f"v13_improved_{suffix}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def run_v13_baseline(*, write=True):
    """V1.2-style router/tool-calling baseline on the V1.3 cases.

    It has no explicit evidence plan or provenance graph; those metrics are
    intentionally zero rather than reconstructed after the fact.
    """
    cases = load_workflow_cases(); agent = build_agent(profile="improved")
    rows=[]
    intent_map={"DATA_QUERY":"growth_status","SENSOR_QUERY":"growth_status","RGB_ANALYSIS":"growth_status",
        "GROWTH_PREDICTION":"growth_forecast","KNOWLEDGE_QA":"knowledge_qa",
        "COMPREHENSIVE_ANALYSIS":"comprehensive_diagnosis","UNSUPPORTED_REQUEST":"knowledge_qa"}
    for case in cases:
        run=agent.ask(case.query,debug=True,trace_id=f"v13-baseline-{case.case_id}")
        workflow=intent_map.get(run.state.intent.value if run.state.intent else "", "unknown")
        actual_tools=[record.tool_name for record in run.state.tool_calls]
        conflict=run.answer.case_model_agreement
        answerability="ABSTAIN" if run.answer.status in ("unsupported","error") else ("PARTIAL" if run.answer.status=="partial" else "FULL")
        rows.append({"case_id":case.case_id,"workflow":workflow,"workflow_ok":workflow==case.expected_workflow,
            "tools":actual_tools,"tools_ok":actual_tools==case.expected_tools,"conflict":conflict,
            "conflict_ok":conflict==case.expected_conflict,"answerability":answerability,
            "answerability_ok":answerability==case.expected_answerability,
            "tool_calls":len(actual_tools),"provider_calls":run.state.llm_calls,"latency_ms":run.state.elapsed_ms})
    n=len(rows); total_tools=sum(row["tool_calls"] for row in rows)
    metrics={"n_cases":n,"workflow_selection_accuracy":mean(float(r["workflow_ok"]) for r in rows),
        "evidence_plan_accuracy":0.0,"required_evidence_completion":0.0,
        "task_success":mean(float(r["workflow_ok"] and r["tools_ok"] and r["answerability_ok"]) for r in rows),
        "unnecessary_tool_rate":sum(sum(t not in next(c for c in cases if c.case_id==r["case_id"]).expected_tools for t in r["tools"]) for r in rows)/total_tools if total_tools else 0.0,
        "conflict_detection_accuracy":mean(float(r["conflict_ok"]) for r in rows),
        "abstention_accuracy":mean(float(r["answerability_ok"]) for r in rows),
        "partial_answer_accuracy":mean(float(r["answerability_ok"]) for r in rows if next(c for c in cases if c.case_id==r["case_id"]).expected_answerability=="PARTIAL"),
        "claim_grounding_rate":0.0,"provenance_completeness":0.0,
        "unsupported_claim_rate":0.0,"hallucinated_value_rate":0.0,"scope_violation_rate":0.0,
        "average_tool_calls":mean(r["tool_calls"] for r in rows),"average_provider_calls":mean(r["provider_calls"] for r in rows)}
    payload={"benchmark":"V1.2-style deterministic baseline","profile":"v13_baseline","metrics":metrics,"results":rows}
    if write:
        destination=PROJECT/"outputs/evals/v13_baseline_results.json"; destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    return payload


def run_v13_comparison():
    baseline_path=PROJECT/"outputs/evals/v13_workflow_baseline_results.json"
    if not baseline_path.exists():
        raise FileNotFoundError("Run and preserve the first-pass V1.3 workflow benchmark before comparison")
    baseline=json.loads(baseline_path.read_text(encoding="utf-8")); improved=run_v13_evaluation(write=True)
    keys=["workflow_selection_accuracy","evidence_plan_accuracy","required_evidence_completion","task_success",
          "unnecessary_tool_rate","conflict_detection_accuracy","abstention_accuracy","partial_answer_accuracy",
          "claim_grounding_rate","provenance_completeness","unsupported_claim_rate","hallucinated_value_rate",
          "scope_violation_rate","average_tool_calls","average_provider_calls"]
    comparison={key:{"baseline":baseline["metrics"].get(key),"improved":improved["metrics"].get(key),
        "delta":improved["metrics"].get(key)-baseline["metrics"].get(key)} for key in keys}
    destination=PROJECT/"outputs/evals/v13_baseline_vs_improved.json"
    destination.write_text(json.dumps({"comparison":comparison},ensure_ascii=False,indent=2),encoding="utf-8")
    return baseline,improved,comparison
