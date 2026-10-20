from .base import BaseWorkflow
from ..evidence.schemas import WorkflowName


class GrowthForecastWorkflow(BaseWorkflow):
    name = WorkflowName.GROWTH_FORECAST

    def tool_names(self, plan):
        prediction = "analyze_rgb" if self.is_view(plan) else "predict_height_t7"
        return ["get_growth_context", prediction, "find_similar_cases", "assess_prediction_reliability"]
