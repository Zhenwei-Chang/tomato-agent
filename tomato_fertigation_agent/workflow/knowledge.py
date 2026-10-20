from .base import BaseWorkflow
from ..evidence.schemas import WorkflowName


class KnowledgeQAWorkflow(BaseWorkflow):
    name = WorkflowName.KNOWLEDGE_QA

    def tool_names(self, plan):
        return ["retrieve_water_fertilizer_knowledge"]
