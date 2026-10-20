from .base import BaseWorkflow
from ..evidence.schemas import WorkflowName


class ComprehensiveDiagnosisWorkflow(BaseWorkflow):
    name = WorkflowName.COMPREHENSIVE_DIAGNOSIS

    def tool_names(self, plan):
        prediction = "analyze_rgb" if self.is_view(plan) else "predict_height_t7"
        return ["get_growth_context", "get_sensor_history", prediction, "find_similar_cases",
                "retrieve_water_fertilizer_knowledge", "assess_prediction_reliability"]
