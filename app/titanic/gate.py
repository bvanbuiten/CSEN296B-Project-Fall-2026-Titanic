"""Authorization / policy gate: the independent control between every agent and its tools.

The model decides which tool to try. The gate decides whether the call may run,
using only code, the database, and config.py. Nothing the model reads or writes can
change these checks. Outcomes:
    allow     - the tool runs
    deny      - the tool does not run
    escalate  - the tool does not run; the case goes to a human supervisor
Each decision names the rule it applied (R1-R7, ORDER, SCOPE, TOOL).
"""
from dataclasses import dataclass

from . import config


@dataclass
class Decision:
    outcome: str
    rule: str = ''
    reason: str = ''

    @property
    def allowed(self):
        return self.outcome == 'allow'

    def as_dict(self):
        return {'outcome': self.outcome, 'rule': self.rule, 'reason': self.reason}


ALLOW = Decision('allow')

# Which agent may call which tool (least privilege). Anything else is denied.
AGENT_TOOLS = {
    'intake': {'create_case', 'flag_case', 'assign_case', 'get_case'},
    'email': {'send_email', 'read_email', 'label_email', 'list_inbox', 'list_mailbox', 'get_case', 'get_customer_profile'},
    'records': {'get_customer_profile', 'get_order', 'list_orders', 'search_case_files', 'get_case',
                'save_case_note', 'apply_deposit', 'get_account_summary', 'upload_policy', 'list_policies'},
    'refund': {'get_case', 'get_order', 'search_policies', 'issue_refund', 'escalate_to_supervisor', 'deny_refund'},
    'reporting': {'get_case', 'record_decision_report', 'list_decisions', 'weekly_autonomous_total'},
}


class PolicyGate:
    def __init__(self, store):
        self.store = store

    # --- shared checks -----------------------------------------------------------
    def _authority(self):
        auth = self.store.authority()
        if not auth or auth['status'] != 'active':
            return Decision('deny', 'R6', 'The agent\'s authority is revoked. No actions until a supervisor restores it.')
        return None

    def _scope_customer(self, ctx, customer_id, what):
        if ctx.get('role') == 'supervisor':
            return None
        if customer_id != ctx.get('session_customer'):
            return Decision('deny', 'R3', f'{what} belongs to a different customer than the one on this request.')
        return None

    def _case(self, ctx, case_id):
        case = self.store.case(case_id) if case_id else None
        if not case:
            return None, Decision('deny', 'SCOPE', f'Case {case_id} does not exist.')
        bad = self._scope_customer(ctx, case['customer_id'], 'This case')
        return case, bad

    # --- main entry ------------------------------------------------------------------
    def check(self, agent, tool, params, ctx):
        if tool not in AGENT_TOOLS.get(agent, set()):
            return Decision('deny', 'R4', f'The {agent} agent is not permitted to use "{tool}". '
                                          'No agent can change permissions, limits, or settings.')
        revoked = self._authority()
        if revoked:
            return revoked
        if 'customer_id' in params:
            bad = self._scope_customer(ctx, params['customer_id'], 'That customer record')
            if bad:
                return bad
        if 'order_id' in params:
            order = self.store.order(params['order_id'])
            if not order:
                return Decision('deny', 'SCOPE', f'Order {params["order_id"]} does not exist.')
            bad = self._scope_customer(ctx, order['customer_id'], 'That order')
            if bad:
                return bad
        if 'case_id' in params and (params['case_id'] or tool != 'send_email'):
            _, bad = self._case(ctx, params['case_id'])
            if bad:
                return bad
        handler = getattr(self, f'_check_{tool}', None)
        return handler(params, ctx) if handler else ALLOW

    # --- tool-specific checks --------------------------------------------------------
    def _check_create_case(self, params, ctx):
        form = ctx.get('form') or {}
        order = self.store.order(form.get('order_id', ''))
        if not order:
            return Decision('deny', 'SCOPE', 'The order on the form does not exist.')
        return self._scope_customer(ctx, order['customer_id'], 'The order on the form') or ALLOW

    def _check_issue_refund(self, params, ctx):
        case = self.store.case(params['case_id'])
        sup = self.store.supervisor_decision(case['id'])
        if sup:
            return Decision('deny', 'R5', f'A supervisor already decided this case ({sup["decision"]}). The agent cannot change it.')
        if case['status'] == 'awaiting_supervisor':
            return Decision('deny', 'R5', 'This case is waiting for a supervisor. The agent cannot approve its own escalation.')
        if case['status'] in ('refunded', 'denied'):
            return Decision('deny', 'SCOPE', f'This case is already closed ({case["status"]}).')
        order = self.store.order(case['order_id'])
        amount = case['requested_cents']
        refundable = order['amount_cents'] - self.store.refunded_on_order(order['id'])
        if amount <= 0:
            return Decision('deny', 'ORDER', 'The refund amount must be more than $0.00.')
        if amount > refundable:
            return Decision('deny', 'ORDER', f'{config.money(amount)} is more than the {config.money(refundable)} '
                                             f'still refundable on order {order["id"]}.')
        if amount > config.PER_REFUND_LIMIT_CENTS:
            return Decision('escalate', 'R1', f'{config.money(amount)} is over the {config.money(config.PER_REFUND_LIMIT_CENTS)} '
                                              'per-refund limit. A supervisor must decide.')
        since = (self.store.clock() - config.WEEKLY_WINDOW).isoformat()
        week_total = self.store.autonomous_total_since(since)
        if week_total + amount > config.WEEKLY_LIMIT_CENTS:
            return Decision('escalate', 'R2', f'Approving {config.money(amount)} would bring the agent\'s 7-day total to '
                                              f'{config.money(week_total + amount)}, over the {config.money(config.WEEKLY_LIMIT_CENTS)} '
                                              'weekly limit. A supervisor must decide.')
        return ALLOW

    def _check_deny_refund(self, params, ctx):
        case = self.store.case(params['case_id'])
        if self.store.supervisor_decision(case['id']) or case['status'] == 'awaiting_supervisor':
            return Decision('deny', 'R5', 'A supervisor owns this case. The agent cannot override it.')
        return ALLOW

    def _check_send_email(self, params, ctx):
        to = (params.get('to') or '').strip().lower()
        case = self.store.case(params['case_id']) if params.get('case_id') else None
        owner_id = case['customer_id'] if case else ctx.get('session_customer')
        owner = self.store.customer(owner_id) if owner_id else None
        allowed = set(config.INTERNAL_ALLOWLIST)
        if owner:
            allowed.add(owner['email'].lower())
        if to not in allowed:
            return Decision('deny', 'R7', f'"{to}" is not the customer\'s address on file or an approved internal address.')
        body = f'{params.get("subject", "")}\n{params.get("body", "")}'.lower()
        for other in self.store.q('SELECT id, email, bank_account FROM customers'):
            if owner and other['id'] == owner['id']:
                continue
            for marker in (other['id'], other['email'], other['bank_account']):
                if marker.lower() in body:
                    return Decision('deny', 'R3', 'The email contains another customer\'s information.')
        return ALLOW

    def _check_read_email(self, params, ctx):
        msg = self.store.one('SELECT * FROM emails WHERE id=?', (params.get('email_id'),))
        if not msg:
            return Decision('deny', 'SCOPE', 'That email does not exist.')
        return self._scope_customer(ctx, msg['customer_id'], 'That email') or ALLOW

    _check_label_email = _check_read_email

    def _check_apply_deposit(self, params, ctx):
        dep = self.store.deposit(params.get('deposit_id', ''))
        if not dep:
            return Decision('deny', 'SCOPE', 'That deposit request does not exist.')
        if dep['status'] != 'pending':
            return Decision('deny', 'SCOPE', 'That deposit was already applied.')
        return self._scope_customer(ctx, dep['customer_id'], 'That deposit') or ALLOW

    def _check_upload_policy(self, params, ctx):
        if ctx.get('role') != 'supervisor':
            return Decision('deny', 'R4', 'Only a supervisor can upload policies.')
        return ALLOW

    def _check_list_policies(self, params, ctx):
        if ctx.get('role') != 'supervisor':
            return Decision('deny', 'R4', 'Only a supervisor can list policy documents.')
        return ALLOW

    # --- human decisions (supervisor portal) -------------------------------------------------
    def check_supervisor_decision(self, case_id, approve):
        """A supervisor's approve/deny enters through the gate too. It is a human decision, so R1, R2,
        and R6 do not apply, but the case must be waiting for a supervisor and the amount must still fit the order."""
        case = self.store.case(case_id)
        if not case or case['status'] != 'awaiting_supervisor':
            return Decision('deny', 'R5', 'That case is not waiting for a supervisor.')
        if approve:
            order = self.store.order(case['order_id'])
            refundable = order['amount_cents'] - self.store.refunded_on_order(order['id'])
            if case['requested_cents'] > refundable:
                return Decision('deny', 'ORDER', f'Cannot approve more than the {config.money(refundable)} still refundable.')
        return ALLOW

    def _check_list_decisions(self, params, ctx):
        return ALLOW  # results are filtered to the session customer unless the caller is a supervisor
