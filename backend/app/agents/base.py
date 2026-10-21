"""Common agent plumbing.

Every agent:
  * receives an AgentContext (db session, run, file, runtime settings, LLM client)
  * does ONE stage of the pipeline and writes its output onto the PipelineRun
  * logs every meaningful action to Operational Memory (the activity feed)
  * works without an LLM: AI is used for semantic judgement, and every AI step
    has a deterministic fallback so the pipeline never blocks on the model.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models import BdxFile, PipelineRun
from app.llm.client import LLMClient
from app.memory import operational


@dataclass
class AgentContext:
    db: Session
    file: BdxFile
    run: PipelineRun
    settings: dict                    # runtime pipeline settings
    user_email: str = "system"
    cache: dict = field(default_factory=dict)   # in-memory datasets shared between stages

    def recorder(self, agent: str):
        def _rec(action, detail, model, tin, tout, ms):
            operational.record(self.db, agent, action, detail, run_id=self.run.id, file_id=self.file.id,
                               model=model, input_tokens=tin, output_tokens=tout, duration_ms=ms)
        return _rec


class BaseAgent(ABC):
    name = "Agent"

    def __init__(self, ctx: AgentContext):
        self.ctx = ctx
        self.llm = LLMClient(recorder=ctx.recorder(self.name))

    def log(self, action: str, detail: str = "", level: str = "info") -> None:
        operational.record(self.ctx.db, self.name, action, detail, run_id=self.ctx.run.id,
                           file_id=self.ctx.file.id, level=level)

    @abstractmethod
    def run(self) -> None: ...
