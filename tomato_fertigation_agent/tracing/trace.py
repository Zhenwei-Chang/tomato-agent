from datetime import datetime, timezone
from threading import Lock
from pathlib import Path
from typing import Any
from uuid import uuid4
from pydantic import Field
from ..schemas.common import Contract


class TraceEvent(Contract):
    trace_id: str
    tool_call_id: str
    request_id: str
    parent_id: str | None = None
    tool_name: str
    arguments_summary: dict = Field(default_factory=dict)
    start_time: datetime
    latency_ms: float
    status: str
    error_code: str | None = None
    result_summary: dict = Field(default_factory=dict)


class TraceWriter:
    def __init__(self, output):
        self.path = output / 'traces/tool_calls.jsonl'
        self.lock = Lock()

    def append(self, event: TraceEvent):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a',encoding='utf-8') as handle:
                handle.write(event.model_dump_json()+'\n')


def summarize(arguments):
    if not isinstance(arguments,dict):
        return {'input_type':type(arguments).__name__}
    summary = {'keys':sorted(arguments), 'n_fields':len(arguments)}
    for key in ('year','date','end_date','window_days','top_k','model_name','requested_scope','scope','retrieval_mode','retrieval_policy','year_filter','treatment_filter'):
        if key in arguments:
            summary[key] = str(arguments[key])[:80]
    if 'query' in arguments:
        summary['query_length'] = len(str(arguments['query']))
    return summary


class AgentTraceEvent(Contract):
    trace_id: str
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    parent_event_id: str | None = None
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    component: str
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    status: str = 'success'
    error_code: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class AgentTraceWriter:
    """Append-only, compact agent trace. Large payloads and secrets are excluded."""
    def __init__(self, output: Path):
        self.path = output / 'traces/agent_traces.jsonl'
        self.lock = Lock()

    def append(self, event: AgentTraceEvent):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8') as handle:
                handle.write(event.model_dump_json() + '\n')
        return event.event_id
