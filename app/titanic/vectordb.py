"""Vector database (Chroma, runs locally). Two collections:

- policies:      refund, privacy/email, and supervisor policies (admin can upload more)
- case_profiles: customer case files and profile summaries, tagged with customer_id

Searches of case_profiles are always filtered to one customer_id, which the policy
gate supplies from the session, so a search can never return another customer's files (R3).
The first run downloads Chroma's small embedding model (all-MiniLM-L6-v2, about 80 MB).
"""
import json

import chromadb

from . import config


class VectorDB:
    def __init__(self, path):
        self.client = chromadb.PersistentClient(path=str(path))
        self.policies = self.client.get_or_create_collection('policies')
        self.case_profiles = self.client.get_or_create_collection('case_profiles')

    def seed(self, store, seed_dir=config.SEED_DIR):
        for p in store.policies():
            self.add_policy(p['id'], p['title'], p['body'])
        for f in json.loads((seed_dir / 'case_files.json').read_text()):
            self.add_case_file(f['id'], f['customer_id'], f['title'], f['text'])

    def add_policy(self, policy_id, title, body):
        # one chunk per section so retrieval returns the relevant rule
        chunks = [c.strip() for c in body.split('\n## ') if c.strip()]
        self.policies.upsert(
            ids=[f'{policy_id}#{i}' for i in range(len(chunks))],
            documents=chunks,
            metadatas=[{'policy_id': policy_id, 'title': title} for _ in chunks])

    def add_case_file(self, file_id, customer_id, title, text):
        self.case_profiles.upsert(ids=[file_id], documents=[text],
                                  metadatas=[{'customer_id': customer_id, 'title': title}])

    def search_policies(self, query, k=3):
        r = self.policies.query(query_texts=[query], n_results=k)
        return [{'id': i, 'title': m['title'], 'text': d}
                for i, d, m in zip(r['ids'][0], r['documents'][0], r['metadatas'][0])]

    def search_case_files(self, query, customer_id, k=3):
        r = self.case_profiles.query(query_texts=[query], n_results=k, where={'customer_id': customer_id})
        return [{'id': i, 'title': m['title'], 'customer_id': m['customer_id'], 'text': d}
                for i, d, m in zip(r['ids'][0], r['documents'][0], r['metadatas'][0])]
