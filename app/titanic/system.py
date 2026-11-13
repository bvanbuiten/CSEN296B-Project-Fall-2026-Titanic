"""Wires Titanic together: memory and databases, audit log, policy gate and tools, agents, orchestrator.

Each TitanicSystem has its own data directory, so red-team tests run against a fresh,
throwaway copy (a sandbox) and never touch the demo data.
"""
from pathlib import Path

from . import config
from .agents import build_mcp_servers
from .audit import AuditLog
from .orchestrator import Orchestrator
from .store import Store
from .tools import ToolRuntime
from .vectordb import VectorDB


class TitanicSystem:
    def __init__(self, data_dir=None, clock=None, mode=None):
        self.data_dir = Path(data_dir or config.DEFAULT_RUNTIME_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.clock = clock or config.utcnow
        self.store = Store(self.data_dir / 'titanic.db', self.clock)
        self.audit = AuditLog(self.data_dir / 'audit.jsonl', self.clock)
        self.vectordb = VectorDB(self.data_dir / 'chroma')
        if not self.store.is_seeded():
            self.store.seed()
            self.vectordb.seed(self.store)
            self.audit.write('system', 'seeded', data_dir=str(self.data_dir.name))
        self.runtime = ToolRuntime(self.store, self.vectordb, self.audit)
        self.mode = mode or config.model_mode()
        self.llm = None
        if self.mode == 'claude':
            from .llm import ClaudeLLM
            self.llm = ClaudeLLM(self.audit)
        self.mcp_servers = build_mcp_servers(self)
        self.orchestrator = Orchestrator(self)

    def reset_demo(self, supervisor):
        """Reload the synthetic demo data. The old audit log is archived, not deleted."""
        tables = [r['name'] for r in self.store.q("SELECT name FROM sqlite_master WHERE type='table'")]
        for t in tables:
            self.store.x(f'DELETE FROM {t}')
        for name in ('policies', 'case_profiles'):
            self.vectordb.client.delete_collection(name)
        self.vectordb = VectorDB(self.data_dir / 'chroma')
        self.runtime.vectordb = self.vectordb
        archived = self.data_dir / f'audit-archive-{self.clock().strftime("%Y%m%dT%H%M%S")}.jsonl'
        if self.audit.path.exists():
            self.audit.path.rename(archived)
        self.audit = AuditLog(self.data_dir / 'audit.jsonl', self.clock)
        self.runtime.audit = self.runtime.payments.audit = self.runtime.mail.audit = self.audit
        if self.llm:
            self.llm.audit = self.audit
        self.orchestrator.audit = self.audit
        self.store.seed()
        self.vectordb.seed(self.store)
        self.audit.write(f'supervisor:{supervisor}', 'demo_reset', archived_log=archived.name)
