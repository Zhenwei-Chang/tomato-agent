def render_answer(answer):
    lines=['# 分析结果','',answer.summary,'','## 数据与预测','']
    if answer.facts:
        for fact in answer.facts:
            value=fact.value if not isinstance(fact.value,dict) else '[结构化数据]'
            unit=f' {fact.unit}' if fact.unit else ''
            lines.append(f'- {fact.name}: {value}{unit}（范围：{fact.scope.value}；来源：观测/数据工具）')
    if answer.predictions:
        for pred in answer.predictions:
            horizon=f'，预测期 {pred.horizon_days} 天' if pred.horizon_days else ''
            lines.append(f'- {pred.name}: {pred.value:.3f} {pred.unit}（范围：{pred.scope.value}{horizon}；模型预测）')
    if not answer.facts and not answer.predictions: lines.append('- 无可用结构化数值结果。')
    lines += ['','## 历史案例证据','']
    if answer.historical_cases:
        for case in answer.historical_cases:
            outcome=case.historical_outcome
            lines.append(f"- {case.case_id}: similarity={case.similarity:.3f}，t+7={outcome.get('height_t7_cm'):.2f} cm，Δ={outcome.get('delta_height_cm'):.2f} cm（范围：{case.scope.value}）")
        if answer.case_prediction_height_t7_cm is not None:
            lines.append(f'- 相似度加权历史结果：{answer.case_prediction_height_t7_cm:.2f} cm；与模型关系：{answer.case_model_agreement}')
    else: lines.append('- 本回答未使用历史 Case Memory。')
    lines += ['','## 依据','']
    if answer.evidence:
        lines += [f'- [{e.evidence_id}] {e.source} {e.locator}'.rstrip() for e in answer.evidence]
    else: lines.append('- 本回答未使用知识库证据；数值只来自已列出的数据/模型工具。')
    lines += ['','## 可信度与限制','',f'- 可信度：{answer.confidence.value}',f'- 证据充分性：{answer.evidence_sufficiency.value}']
    lines += [f'- 警告：{x}' for x in answer.warnings]
    lines += [f'- 限制：{x}' for x in answer.limitations]
    lines += [f'- 当前不支持：{x}' for x in answer.unsupported_requests]
    return '\n'.join(lines)
