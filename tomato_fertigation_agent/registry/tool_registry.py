from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4
import json
from pydantic import ValidationError
from ..config import Settings
from ..schemas.common import ToolMetadata, ToolResult, ToolError, ToolFailure, ErrorCode, Scope
from ..schemas.tools import ContextInput, SensorInput, TreatmentInput, PredictionInput, ImageInput, RGBInput, KnowledgeInput, ReliabilityInput, SimilarCasesInput
from ..schemas.outputs import OUTPUTS
from ..adapters.multimodal_adapter import MultimodalAdapter
from ..adapters.model_adapter import ModelAdapter, VisionAdapter
from ..adapters.rag_adapter import RAGAdapter
from ..adapters.loading import json_clean
from ..tracing.trace import TraceEvent, TraceWriter, summarize
from ..tools.growth import get_growth_context
from ..tools.sensor import get_sensor_history
from ..tools.treatment import get_treatment_recipe
from ..tools.prediction import predict_height_t7
from ..tools.vision import analyze_rgb, get_image_embedding
from ..tools.knowledge import retrieve_water_fertilizer_knowledge
from ..tools.reliability import assess_prediction_reliability
from ..tools.similar_cases import find_similar_cases
from ..cases import CaseRepository, PlantCaseRetriever, ViewCaseRetriever


def _strict_schema(model):
    """Create the strict JSON Schema required by OpenAI function tools.

    Optional application fields remain nullable, but are listed as required so
    the model explicitly emits null/default values. Pydantic validation remains
    the final authority before a tool executes.
    """
    schema = model.model_json_schema()
    def visit(node):
        if isinstance(node, dict):
            if node.get('type') == 'object' or 'properties' in node:
                node['additionalProperties'] = False
                node['required'] = list(node.get('properties', {}).keys())
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(schema)
    return schema


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type
    scope: str
    handler: object
    version: str = '1.0.0'


class ToolRegistry:
    CONTRACT_VERSION = 'v1.4.3-evidence'

    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.data = MultimodalAdapter(self.settings)
        self.models = ModelAdapter(self.data)
        self.vision = VisionAdapter(self.data,self.models)
        self.rag = RAGAdapter(self.settings)
        self.case_repository = CaseRepository(self.settings.workspace / 'tomato_fertigation_agent')
        self.plant_cases = PlantCaseRetriever(self.case_repository)
        self.view_cases = ViewCaseRetriever(self.case_repository)
        self.trace = TraceWriter(self.settings.output)
        definitions = [
            ToolDefinition('get_growth_context','Query exact-date phenotype, environment and image availability; preserve scope and nulls.',ContextInput,'dataset',lambda a:get_growth_context(self.data,a)),
            ToolDefinition('get_sensor_history','Query daily global sensor history; substrate values are global proxies.',SensorInput,'greenhouse',lambda a:get_sensor_history(self.data,a)),
            ToolDefinition('get_treatment_recipe','Query existing fertilizer recipe and derived nutrient composition; not event volumes.',TreatmentInput,'treatment',lambda a:get_treatment_recipe(self.data,a)),
            ToolDefinition('predict_height_t7','Experimental plant height forecast from complete 7-day history and current observed height/LAI.',PredictionInput,'plant',lambda a:predict_height_t7(self.data,self.models,a)),
            ToolDefinition('analyze_rgb','View mean height estimates from frozen ResNet18; not single-plant phenotype.',RGBInput,'view',lambda a:analyze_rgb(self.data,self.vision,a)),
            ToolDefinition('get_image_embedding','Return 512D frozen ResNet18 representation for View image; not calibrated similarity.',ImageInput,'view',lambda a:get_image_embedding(self.data,self.vision,a)),
            ToolDefinition('retrieve_water_fertilizer_knowledge','Reuse existing local RAG retrieval with evidence and applicability boundaries; no answer synthesis.',KnowledgeInput,'knowledge',lambda a:retrieve_water_fertilizer_knowledge(self.rag,a)),
            ToolDefinition('assess_prediction_reliability','Rule-based reliability assessment; not statistically calibrated confidence.',ReliabilityInput,'dataset',assess_prediction_reliability),
            ToolDefinition('find_similar_cases','Retrieve leakage-safe historical Plant or View cases with observed exact +7-day outcomes; association is not causality.',SimilarCasesInput,'dataset',lambda a:find_similar_cases(self.case_repository,self.plant_cases,self.view_cases,a),'1.2.0'),
        ]
        self.definitions = {d.name:d for d in definitions}

    def discover(self):
        return [{'name':d.name,'description':d.description,'version':d.version,'scope':d.scope,
                 'input_schema':d.input_model.model_json_schema(),'output_schema':self.output_schema(d.name)} for d in self.definitions.values()]

    @property
    def canonical_names(self):
        """Canonical executable names, in deterministic registry order."""
        return tuple(self.definitions)

    def router_catalog(self):
        """Compact router contract derived from the executable registry.

        The router receives this catalog on every call.  There is deliberately
        no alias or fuzzy-name layer between this contract and execution.
        """
        return [{'name':d.name,'description':d.description,'scope':d.scope,
                 'input_schema':d.input_model.model_json_schema()}
                for d in self.definitions.values()]

    def validate_tool_names(self, names, *, require_nonempty=False):
        values=list(names or [])
        unknown=[name for name in values if name not in self.definitions]
        duplicates=list(dict.fromkeys(name for name in values if values.count(name)>1))
        valid=not unknown and not duplicates and (bool(values) or not require_nonempty)
        return {'valid':valid,'unknown':unknown,'duplicates':duplicates,
                'empty':not values,'canonical_names':list(self.canonical_names)}

    def output_schema(self,name):
        schema = ToolResult.model_json_schema()
        payload = OUTPUTS[name].model_json_schema()
        schema.setdefault('$defs',{}).update(payload.pop('$defs',{}))
        schema['allOf'] = [{'if':{'properties':{'status':{'enum':['success','partial']}}},
                            'then':{'properties':{'data':payload}}}]
        return schema

    def function_schemas(self):
        return [{'name':d.name,'description':d.description,'parameters':d.input_model.model_json_schema()} for d in self.definitions.values()]

    def export_function_schemas(self, provider='openai', names=None):
        """Export provider schemas from the canonical Pydantic contracts.

        This deliberately has no second hand-written function-schema source.
        """
        selected = [self.definitions[name] for name in (names or self.definitions) if name in self.definitions]
        if provider == 'openai':
            return [{'type':'function','function':{'name':d.name,'description':d.description,
                    'parameters':_strict_schema(d.input_model),'strict':True}} for d in selected]
        if provider == 'openai_responses':
            return [{'type':'function','name':d.name,'description':d.description,
                    'parameters':_strict_schema(d.input_model),'strict':True} for d in selected]
        if provider in ('generic','mock'):
            return [{'name':d.name,'description':d.description,'parameters':d.input_model.model_json_schema()} for d in selected]
        raise ValueError(f'Unsupported function-schema provider: {provider}')

    def validate_arguments(self, name, arguments):
        definition = self.definitions.get(name)
        if definition is None:
            raise ValueError(f'Unknown tool: {name}')
        return definition.input_model.model_validate(arguments).model_dump(mode='json', exclude_none=True)

    def call(self, name, arguments, *, trace_id=None, parent_id=None, request_id=None):
        started = datetime.now(timezone.utc); clock = perf_counter()
        call_id = str(uuid4()); trace_id = trace_id or str(uuid4()); request_id = request_id or str(uuid4())
        definition = self.definitions.get(name)
        metadata = ToolMetadata(tool_name=name,tool_version=definition.version if definition else '1.0.0',scope=definition.scope if definition else 'dataset',trace_id=trace_id,tool_call_id=call_id)
        trace_summary = {}
        try:
            if definition is None:
                raise ToolFailure(ErrorCode.INVALID_ARGUMENT,'Unknown tool name',tool_name=name)
            try:
                parsed = definition.input_model.model_validate(arguments)
            except ValidationError as exc:
                raise ToolFailure(ErrorCode.INVALID_ARGUMENT,'Input schema validation failed',issues=[{'location':list(e['loc']),'type':e['type']} for e in exc.errors()]) from exc
            if name == 'find_similar_cases':
                metadata = metadata.model_copy(update={'scope': Scope(parsed.scope)})
            outcome = definition.handler(parsed)
            trace_summary = outcome.trace_summary
            evidence = json_clean(outcome.evidence)
            metadata = ToolMetadata.model_validate({**metadata.model_dump(), 'scope':outcome.scope, 'data_source':list(dict.fromkeys(e['source'] for e in evidence)),
                'model_version':outcome.model_version,'confidence':outcome.confidence,'confidence_reason':outcome.reasons,'limitations':outcome.limitations})
            payload = OUTPUTS[name].model_validate(json_clean(outcome.data)).model_dump(mode='json')
            result = ToolResult(status=outcome.status,data=payload,metadata=metadata,warnings=outcome.warnings,evidence=evidence)
            json.dumps(result.model_dump(mode='json'),allow_nan=False)
        except ToolFailure as exc:
            result = ToolResult(status='error',metadata=metadata,error=ToolError(code=exc.code,message=str(exc),details=exc.details))
        except (ImportError,ModuleNotFoundError) as exc:
            result = ToolResult(status='error',metadata=metadata,error=ToolError(code=ErrorCode.DEPENDENCY_ERROR,message='Required runtime dependency unavailable',details={'type':type(exc).__name__}))
        except FileNotFoundError as exc:
            result = ToolResult(status='error',metadata=metadata,error=ToolError(code=ErrorCode.DATA_NOT_FOUND,message='Required asset not found'))
        except Exception as exc:
            result = ToolResult(status='error',metadata=metadata,error=ToolError(code=ErrorCode.INTERNAL_ERROR,message='Tool execution failed',details={'type':type(exc).__name__}))
        try:
            self.trace.append(TraceEvent(trace_id=trace_id,tool_call_id=call_id,request_id=request_id,parent_id=parent_id,tool_name=name,
                arguments_summary=summarize(arguments),start_time=started,latency_ms=(perf_counter()-clock)*1000,
                status=result.status,error_code=result.error.code.value if result.error else None,result_summary=trace_summary))
        except OSError:
            return ToolResult(status='error',metadata=metadata,error=ToolError(code=ErrorCode.DEPENDENCY_ERROR,message='Trace output unavailable'),warnings=['Tool result withheld because trace could not be persisted'])
        return result
