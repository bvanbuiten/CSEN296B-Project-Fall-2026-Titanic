"""Negative controls: prove each red-team test can fail.

For each test, switch off the one control it checks (in memory only; no files are changed),
run the test, and confirm it reports FAIL. Then run it again with the control on and confirm PASS.
Results go to redteam/results/negative-controls.json.

Run from the repo root:  python redteam/negative_controls.py
"""
import asyncio
import json
import os
import sys
from contextlib import ExitStack, contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.titanic import config, redteam  # noqa: E402
from app.titanic.gate import PolicyGate  # noqa: E402
from app.titanic.orchestrator import Orchestrator  # noqa: E402


@contextmanager
def patched(obj, name, value):
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)


def no_scope(self, ctx, customer_id, what):          # breaks R3 record scoping
    return None


def no_authority(self):                                # breaks R6 at the gate
    return None


def weekly_off(self, params, ctx):                     # breaks R2 (keeps R1)
    case = self.store.case(params['case_id'])
    if case['requested_cents'] > config.PER_REFUND_LIMIT_CENTS:
        from app.titanic.gate import Decision
        return Decision('escalate', 'R1', 'over $100')
    from app.titanic.gate import ALLOW
    return ALLOW


def r7_off(self, params, ctx):                         # breaks R7 recipient allowlist and the R3 email check
    from app.titanic.gate import ALLOW
    return ALLOW


async def orchestrator_ignores_revocation(self, kind, identity, payload=None):
    auth = self.store.authority
    self.store.authority = lambda: {'status': 'active', 'changed_at': ''}
    try:
        return await ORIGINAL_HANDLE(self, kind, identity, payload)
    finally:
        self.store.authority = auth


ORIGINAL_HANDLE = Orchestrator.handle

CONTROLS = [
    ('rt-05', 'R3 record scoping turned off in the policy gate', [(PolicyGate, '_scope_customer', no_scope)]),
    ('rt-06', 'R2 weekly cap check removed from the policy gate', [(PolicyGate, '_check_issue_refund', weekly_off)]),
    ('rt-07', 'R7 email recipient check removed from the policy gate', [(PolicyGate, '_check_send_email', r7_off)]),
    ('rt-08', 'R6 revocation check removed from the gate and the orchestrator',
     [(PolicyGate, '_authority', no_authority), (Orchestrator, 'handle', orchestrator_ignores_revocation)]),
]


async def main():
    results = []
    for test_id, broken, patches in CONTROLS:
        runner = redteam.RUNNERS[test_id]
        with ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patched(*patch))
            broken_run = await runner()
        normal_run = await runner()
        b, n = broken_run['summary'], normal_run['summary']
        results.append({'test_id': test_id.upper(), 'control_switched_off': broken,
                        'with_control_off': {'verdict': b['verdict'], 'cases_passed': f'{b["cases_passed"]}/{b["cases_run"]}'},
                        'with_control_on': {'verdict': n['verdict'], 'cases_passed': f'{n["cases_passed"]}/{n["cases_run"]}'},
                        'test_detects_broken_control': b['verdict'] == 'FAIL' and n['verdict'] == 'PASS'})
        print(results[-1])
    out = {'run_at': config.utcnow().isoformat(), 'model_mode': config.model_mode(), 'data': 'synthetic',
           'note': 'Controls were switched off in memory only, inside throwaway sandboxes. RT-02 has its own negative '
                   'controls (see redteam/plan.md).', 'results': results}
    path = os.path.join(os.path.dirname(__file__), 'results', 'negative-controls.json')
    with open(path, 'w') as f:
        json.dump(out, f, indent=2)
    print('saved', path)


if __name__ == '__main__':
    asyncio.run(main())
