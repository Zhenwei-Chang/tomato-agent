from __future__ import annotations

from dataclasses import dataclass

from ..evidence.schemas import WorkflowName
from ..schemas.agent import Intent


@dataclass(frozen=True)
class ReliabilityRequirement:
    required: bool
    model_name: str | None = None
    model_scope: str | None = None
    reason: str = ''


class ReliabilityRequirementMatrix:
    """Application-owned reliability requirements (not LLM recommendations)."""

    VERSION = 'v1.4.5-reliability-matrix-1'

    _INTENTS = {
        Intent.GROWTH_PREDICTION: ReliabilityRequirement(
            True, 'height_v03_b0', 'plant', 'Numerical plant forecast requires reliability assessment'),
        Intent.RGB_ANALYSIS: ReliabilityRequirement(
            True, 'rgb_v05', 'view', 'View-level RGB model output requires reliability assessment'),
        Intent.COMPREHENSIVE_ANALYSIS: ReliabilityRequirement(
            True, 'height_v03_b0', 'plant', 'Comprehensive forecast requires reliability assessment'),
    }
    _WORKFLOWS = {
        WorkflowName.GROWTH_FORECAST: ReliabilityRequirement(
            True, 'height_v03_b0', 'plant', 'Forecast workflow requires reliability assessment'),
        WorkflowName.COMPREHENSIVE_DIAGNOSIS: ReliabilityRequirement(
            True, 'height_v03_b0', 'plant', 'Comprehensive workflow requires reliability assessment'),
    }

    def for_intent(self, intent: Intent | None) -> ReliabilityRequirement:
        return self._INTENTS.get(intent, ReliabilityRequirement(False))

    def for_workflow(self, workflow: WorkflowName | None) -> ReliabilityRequirement:
        return self._WORKFLOWS.get(workflow, ReliabilityRequirement(False))
