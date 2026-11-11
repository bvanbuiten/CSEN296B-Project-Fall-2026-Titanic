"""Governance layer: an append-only, hash-chained audit log.

Every entry stores the hash of the entry before it, so editing or deleting a past
entry breaks the chain and verify() reports where. Tools and the policy gate write
these entries from code; the model cannot write to the log directly.
"""
import hashlib
import json
import threading

from . import config

GENESIS = '0' * 64


def _hash(prev_hash, body):
    payload = prev_hash + json.dumps(body, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


class AuditLog:
    def __init__(self, path, clock=None):
        self.path = path
        self.clock = clock or config.utcnow
        self._lock = threading.Lock()
        self._seq, self._last = 0, GENESIS
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self._seq, self._last = entry['seq'], entry['hash']

    def write(self, actor, event, **details):
        with self._lock:
            body = {'seq': self._seq + 1, 'ts': self.clock().isoformat(), 'actor': actor,
                    'event': event, 'details': details, 'prev_hash': self._last}
            body['hash'] = _hash(self._last, body)
            with open(self.path, 'a') as f:
                f.write(json.dumps(body, default=str) + '\n')
            self._seq, self._last = body['seq'], body['hash']
            return body

    def entries(self, limit=None):
        if not self.path.exists():
            return []
        rows = [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]
        return rows[-limit:] if limit else rows

    def verify(self):
        prev = GENESIS
        for entry in self.entries():
            body = {k: v for k, v in entry.items() if k != 'hash'}
            if entry['prev_hash'] != prev or _hash(prev, body) != entry['hash']:
                return {'ok': False, 'broken_at_seq': entry['seq']}
            prev = entry['hash']
        return {'ok': True, 'entries': self._seq}
