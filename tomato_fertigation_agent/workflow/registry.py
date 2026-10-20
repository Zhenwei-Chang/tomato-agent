from .comprehensive import ComprehensiveDiagnosisWorkflow
from .forecast import GrowthForecastWorkflow
from .knowledge import KnowledgeQAWorkflow
from .status import GrowthStatusWorkflow


class WorkflowRegistry:
    def __init__(self):
        workflows = [GrowthStatusWorkflow(), GrowthForecastWorkflow(), KnowledgeQAWorkflow(),
                     ComprehensiveDiagnosisWorkflow()]
        self.workflows = {workflow.name: workflow for workflow in workflows}

    def get(self, name):
        if name not in self.workflows:
            raise ValueError(f"Unknown workflow: {name}")
        return self.workflows[name]

    def discover(self):
        return [workflow.name.value for workflow in self.workflows.values()]
