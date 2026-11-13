"""Short-term memory: the working state of one request while the orchestrator runs it.

It holds the plan, each agent's result, and the case ID, and is discarded when the
request finishes. Anything worth keeping is written to long-term memory (the database)
as a case note, so the next request about the same case can see it.
"""


class ShortTermMemory:
    def __init__(self, request_id, request):
        self.request_id = request_id
        self.request = request
        self.plan = []
        self.results = []
        self.case_id = None

    def remember(self, agent, action, result):
        self.results.append({'agent': agent, 'action': action, 'result': result})
        if isinstance(result, dict) and result.get('case_id'):
            self.case_id = result['case_id']

    def snapshot(self):
        """Compact view passed to the next agent and to the response aggregator."""
        return {'request_id': self.request_id, 'case_id': self.case_id,
                'completed_steps': [{'agent': r['agent'], 'action': r['action'],
                                     'summary': (r['result'] or {}).get('summary', '')} for r in self.results]}
