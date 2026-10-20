from .schemas import Answerability, DiagnosisResult


def render_diagnosis(result: DiagnosisResult, debug: bool = False) -> str:
    lines = ["# 番茄证据驱动分析", "", result.summary, ""]
    workflow = result.workflow
    if workflow in ("growth_status", "growth_forecast", "comprehensive_diagnosis"):
        lines += ["## 当前状态", ""]
        lines.append(_compact(result.current_state) if result.current_state else "- 无可用的精确日期观测。")
    if workflow in ("growth_status", "comprehensive_diagnosis"):
        lines += ["", "## 最近环境", ""]
        lines.append(_compact(result.sensor_context) if result.sensor_context else "- 最近环境证据不可用。")
    if workflow in ("growth_forecast", "comprehensive_diagnosis"):
        lines += ["", "## 未来预测", ""]
        lines.append(_compact(result.forecast) if result.forecast else "- 当前无法给出可靠预测。")
        lines += ["", "## 历史案例", ""]
        lines.append(_compact(result.historical_context) if result.historical_context else "- 未获得可靠历史案例。")
    if workflow in ("knowledge_qa", "comprehensive_diagnosis"):
        lines += ["", "## 知识依据", ""]
        if result.knowledge_context:
            lines += [f"- [{item['evidence_id']}] {item.get('summary','')}" for item in result.knowledge_context]
        else:
            lines.append("- 没有通过相关性与充分性检查的知识证据。")
    if result.conflicts:
        lines += ["", "## 一致性与冲突", ""]
        lines += [f"- {item.status.value}: {item.explanation}" for item in result.conflicts]
    if result.management_considerations:
        lines += ["", "## 需要关注", ""]
        lines += [f"- {item.level.value}: {item.text}" for item in result.management_considerations]
    if result.unsupported_subtasks:
        lines += ["", "## 当前不能确定", ""]
        lines += [f"- {item.request}：{item.reason}" for item in result.unsupported_subtasks]
    lines += ["", "## 可信度", "",
              f"- 可回答性：{result.answerability.value}",
              f"- 工作流可信度：{result.overall_reliability.level.value}",
              f"- 证据完整性：{result.evidence_completeness.status.value}"]
    lines += [f"- 限制：{item}" for item in result.limitations]
    if debug:
        lines += ["", "## Claim Provenance", ""]
        lines += [f"- {claim.claim_id} → {', '.join(claim.support_evidence_ids) or 'NONE'}" for claim in result.claims]
    return "\n".join(lines)


def _compact(value):
    if not isinstance(value, dict):
        return f"- {value}"
    return "\n".join(f"- {key}: {item}" for key, item in value.items())
