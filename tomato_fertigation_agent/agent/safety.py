import json
import re
from ..schemas.agent import AgentAnswer


class UnsupportedNumericalClaimDetector:
    PATTERN=re.compile(r'(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>mL|毫升|L/株|%|百分比|EC)',re.I)

    def check(self, answer, tool_results):
        source=json.dumps([r.model_dump(mode='json') for r in tool_results],ensure_ascii=False,default=str)
        allowed={m.group(0) for m in re.finditer(r'\d+(?:\.\d+)?',source)}
        text=' '.join([answer.summary]+[x.text for x in answer.agronomic_interpretation+answer.recommendations])
        unsupported=[]
        for match in self.PATTERN.finditer(text):
            if match.group('number') not in allowed: unsupported.append(match.group(0))
        return unsupported


class ScopeSafetyChecker:
    def check(self, answer, requested_scope):
        violations=[]
        for item in answer.predictions:
            if item.source_tool=='analyze_rgb' and item.scope.value!='view': violations.append('RGB_SCOPE_ESCALATION')
            if item.source_tool=='predict_height_t7' and item.scope.value!='plant': violations.append('HEIGHT_SCOPE_ESCALATION')
        if requested_scope and requested_scope.value=='plant' and any(p.source_tool=='analyze_rgb' for p in answer.predictions):
            violations.append('VIEW_RESULT_CANNOT_SATISFY_PLANT_REQUEST')
        if requested_scope and any(c.scope!=requested_scope for c in answer.historical_cases):
            violations.append('CASE_SCOPE_ESCALATION')
        return violations


class AnswerSafetyPipeline:
    def __init__(self):
        self.scope=ScopeSafetyChecker(); self.numeric=UnsupportedNumericalClaimDetector()

    def apply(self, answer: AgentAnswer, requested_scope, tool_results):
        violations=self.scope.check(answer,requested_scope)
        numeric=self.numeric.check(answer,tool_results)
        violations += ['UNSUPPORTED_NUMERICAL_CLAIM']*len(numeric)
        if not violations: return answer,[]
        warnings=list(answer.warnings)+[f'Safety check: {v}' for v in violations]
        unsupported=list(answer.unsupported_requests)
        if numeric: unsupported.append('Unsupported numerical recommendations were blocked: '+', '.join(numeric))
        predictions=answer.predictions
        historical_cases=answer.historical_cases
        if 'VIEW_RESULT_CANNOT_SATISFY_PLANT_REQUEST' in violations:
            predictions=[p for p in predictions if p.source_tool!='analyze_rgb']
            unsupported.append('View-level RGB output cannot answer a plant-specific request')
        if 'CASE_SCOPE_ESCALATION' in violations and requested_scope:
            historical_cases=[c for c in historical_cases if c.scope==requested_scope]
            unsupported.append('Historical cases at another spatial scope cannot answer this request')
        recommendations=[] if numeric else answer.recommendations
        return answer.model_copy(update={'status':'unsupported' if unsupported else 'partial','predictions':predictions,'historical_cases':historical_cases,
            'recommendations':recommendations,'warnings':list(dict.fromkeys(warnings)),
            'unsupported_requests':list(dict.fromkeys(unsupported))}),violations
