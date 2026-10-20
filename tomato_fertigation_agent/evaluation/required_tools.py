from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..agent.reliability_policy import ReliabilityRequirementMatrix
from ..schemas.agent import Intent
from ..evidence.schemas import WorkflowName


@dataclass
class RequiredToolAudit:
    required_tools: list[str] = field(default_factory=list)
    planned: list[str] = field(default_factory=list)
    proposed: list[str] = field(default_factory=list)
    actually_executed: list[str] = field(default_factory=list)
    successfully_completed: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    complete: bool = False

    def to_dict(self):
        return asdict(self)


class IndependentRequiredToolEvaluator:
    """Recompute completion from fixture/contract and execution trace.

    This evaluator never consumes WorkflowState.required_tool_completion.
    """

    VERSION = 'v1.4.5-independent-required-tool-evaluator-1'

    def __init__(self, matrix=None):
        self.matrix=matrix or ReliabilityRequirementMatrix()

    def required_from_case(self, case) -> list[str]:
        """Return policy-mandated tools, independently of model/route output.

        Fixture expected tools continue to drive tool-selection metrics. This
        audit is intentionally narrower: it detects mandatory workflow controls
        such as reliability that a model may omit from its plan.
        """
        required=[]
        requirement=None
        if case.mode=='workflow' and case.expected_workflow:
            requirement=self.matrix.for_workflow(WorkflowName(case.expected_workflow))
        elif case.expected_intent:
            requirement=self.matrix.for_intent(Intent(case.expected_intent))
        if requirement and requirement.required:
            required.append('assess_prediction_reliability')
        return required

    @staticmethod
    def required_from_contract(contract) -> list[str]:
        if not contract:
            return []
        subtasks=contract.get('subtasks',[]) if isinstance(contract,dict) else contract.subtasks
        required=[]
        for row in subtasks:
            value=row if isinstance(row,dict) else row.model_dump(mode='json')
            if (value.get('required') and
                    value.get('source')=='REQUIRED_BY_TASK_POLICY'):
                required.extend(value.get('required_tools') or [])
        return list(dict.fromkeys(required))

    def evaluate(self, *, calls, required_tools, planned_tools=None, warnings=None):
        calls=[row if isinstance(row,dict) else row.model_dump(mode='json') for row in calls]
        required=list(dict.fromkeys(required_tools))
        planned=list(dict.fromkeys(planned_tools or []))
        proposed=list(dict.fromkeys(row['tool_name'] for row in calls
            if row.get('dispatch_source')=='MODEL_GENERATED_TOOL_CALL'))
        executed=list(dict.fromkeys(row['tool_name'] for row in calls
            if row.get('actual_execution',True)))
        reused=list(dict.fromkeys(row['tool_name'] for row in calls
            if row.get('reused_result') and row.get('cached_from_tool_call_id') and
            row.get('result_status') in {'success','partial'}))
        completed=list(dict.fromkeys(row['tool_name'] for row in calls
            if row.get('result_status') in {'success','partial'} and
            (row.get('actual_execution',True) or row['tool_name'] in reused)))
        unavailable=[]
        warning_text=' '.join(warnings or []).lower()
        for name in required:
            if name not in completed and ('budget exhausted' in warning_text or
                    'unavailable' in warning_text or 'failed' in warning_text):
                unavailable.append(name)
        missing=[name for name in required if name not in completed]
        return RequiredToolAudit(required,planned,proposed,executed,completed,reused,
            unavailable,missing,not missing)
