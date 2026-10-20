from .base import BaseWorkflow
from ..evidence.schemas import WorkflowName


class GrowthStatusWorkflow(BaseWorkflow):
    name = WorkflowName.GROWTH_STATUS

    def tool_names(self, plan):
        tools = ["get_growth_context", "get_sensor_history"]
        if self.is_view(plan) and any(req.evidence_type.value == "visual_observation" for req in plan.requirements):
            tools.append("analyze_rgb")
        return tools
