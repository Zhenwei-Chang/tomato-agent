from dataclasses import dataclass, field


@dataclass
class Outcome:
    data: dict
    scope: str
    warnings: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    model_version: str | None = None
    confidence: str = 'UNKNOWN'
    reasons: list = field(default_factory=list)
    limitations: list = field(default_factory=list)
    status: str = 'success'
    trace_summary: dict = field(default_factory=dict)


DATA_LIMITS = ['Public dataset, not live greenhouse data', 'Final processed values do not prove original manual observation',
              'No reliable irrigation volumes or optimal decision labels']
SENSOR_LIMITS = ['Strong cross-season sensor domain shift', 'Substrate variables are greenhouse-global proxies; no reliable probe-to-View mapping']
RGB_LIMITS = ['This prediction is View-level, not Plant-level.', 'Background/View identity shortcut risk', 'Physical View identity across years UNKNOWN']
