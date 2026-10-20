from dataclasses import dataclass, field
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    workspace: Path = field(default_factory=lambda: Path(os.getenv("TOMATO_WORKSPACE", str(PROJECT.parent))).resolve())
    research: Path = field(default_factory=lambda: Path(os.getenv("TOMATO_RESEARCH_ROOT", str(PROJECT.parent / "tomato_multimodal_public"))).resolve())
    raw: Path = field(default_factory=lambda: Path(os.getenv("TOMATO_RAW_ROOT", str(PROJECT / "inputs"))).resolve())
    output: Path = field(default_factory=lambda: Path(os.getenv("TOMATO_OUTPUT_ROOT", str(PROJECT / "outputs"))).resolve())
    inputs: Path = PROJECT / "inputs"

    def __post_init__(self):
        if self.output == self.raw or self.raw in self.output.parents:
            raise ValueError("Output must not be inside read-only raw data")
