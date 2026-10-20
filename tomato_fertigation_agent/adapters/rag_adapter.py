from dataclasses import asdict
import importlib
from pathlib import Path
import sys
from ..schemas.common import ToolFailure, ErrorCode


class RAGAdapter:
    def __init__(self, settings):
        self.settings = settings
        self.repository = None

    def load(self):
        if self.repository is None:
            root = self.settings.workspace
            if not (root/'agent_system/knowledge.py').is_file():
                raise ToolFailure(ErrorCode.DEPENDENCY_ERROR, 'Existing RAG repository not found')
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            module = importlib.import_module('agent_system.knowledge')
            if Path(module.__file__).resolve() != (root/'agent_system/knowledge.py').resolve():
                raise ToolFailure(ErrorCode.DEPENDENCY_ERROR, 'Another workspace RAG module is already imported')
            try:
                self.repository = module.KnowledgeRepository(verify_snapshot=True)
            except RuntimeError as exc:
                raise ToolFailure(ErrorCode.DEPENDENCY_ERROR, 'Existing RAG snapshot verification failed; no bypass') from exc
        return self.repository

    def retrieve(self, args):
        repo = self.load()
        effective = ' '.join(v for v in [args.query,args.growth_stage,args.topic] if v)
        entries = [asdict(e) for e in repo.retrieve(effective, limit=args.top_k)]
        evidence = [{'evidence_id':e['knowledge_id'], 'source':e['title'], 'locator':e['locator'],
                     'content':e['conclusion'], 'score':float(e['score']),
                     'attributes': {**e,'sources':[repo.sources[s] for s in e['source_ids'] if s in repo.sources]}} for e in entries]
        return {'query':args.query,'effective_query':effective,'retrieved_chunks':entries,
                'existing_rag_generated_answer':None,'retrieval_only':True,
                'snapshot_id':repo.snapshot_id,'score_semantics':'existing keyword/rule ranking; not probability',
                'answer_sufficiency':'NOT_ASSESSED'}, evidence
