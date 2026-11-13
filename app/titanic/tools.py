"""Agent tools, the mock services behind them, and the runtime that gates every call.

Flow for every tool call:
    agent tries tool -> audit "tool_attempt" -> PolicyGate.check -> (allow) run tool
    -> audit "tool_result" with the decision and whether it executed.
This gives the three things the spec's assurance framework asks for: did the agent
try something outside its limits, did an independent control allow or deny it, and
did the operation actually execute.
"""
import threading

from . import config
from .gate import Decision, PolicyGate

# Tools that read customer records; every call is written to the records-access log.
RECORD_TOOLS = {'get_customer_profile', 'get_order', 'list_orders', 'search_case_files', 'get_case',
                'get_account_summary', 'read_email', 'save_case_note'}


class MockPaymentService:
    """'Issues' a refund by crediting the customer's Titanic account balance. No real money."""

    def __init__(self, store, audit):
        self.store, self.audit = store, audit

    def refund(self, case, amount_cents, approved_by, autonomous):
        refund_id = self.store.record_refund(case['id'], case['customer_id'], case['order_id'],
                                             amount_cents, approved_by, autonomous)
        self.store.adjust_balance(case['customer_id'], amount_cents)
        self.audit.write('payment-service', 'refund_issued', refund_id=refund_id, case_id=case['id'],
                         customer_id=case['customer_id'], amount=config.money(amount_cents),
                         approved_by=approved_by, autonomous=autonomous)
        return refund_id

    def deposit(self, dep):
        self.store.adjust_balance(dep['customer_id'], dep['amount_cents'])
        self.store.x("UPDATE deposits SET status='applied' WHERE id=?", (dep['id'],))
        self.audit.write('payment-service', 'deposit_applied', deposit_id=dep['id'],
                         customer_id=dep['customer_id'], amount=config.money(dep['amount_cents']))


class MockEmailService:
    """Mock mail server: outbound mail lands in the 'sent' folder; inbound mail in 'inbox'."""

    def __init__(self, store, audit):
        self.store, self.audit = store, audit

    def send(self, to, subject, body, case_id=None, customer_id=None):
        email_id = self.store.add_email('out', 'sent', config.SUPPORT_ADDRESS, to, subject, body, case_id, customer_id)
        self.audit.write('email-service', 'email_sent', email_id=email_id, to=to, subject=subject, case_id=case_id)
        return email_id

    def receive(self, from_addr, subject, body, customer_id):
        email_id = self.store.add_email('in', 'inbox', from_addr, config.SUPPORT_ADDRESS, subject, body,
                                        None, customer_id, label='unprocessed')
        self.audit.write('email-service', 'email_received', email_id=email_id, from_addr=from_addr, subject=subject)
        return email_id


def _public_case(case):
    keys = ('id', 'customer_id', 'order_id', 'channel', 'requested_cents', 'reason', 'status',
            'assigned_to', 'flags', 'decision', 'decision_reason', 'created_at')
    out = {k: case.get(k) for k in keys}
    out['requested'] = config.money(case['requested_cents'])
    return out


class ToolRuntime:
    def __init__(self, store, vectordb, audit):
        self.store, self.vectordb, self.audit = store, vectordb, audit
        self.gate = PolicyGate(store)
        self.payments = MockPaymentService(store, audit)
        self.mail = MockEmailService(store, audit)
        self._lock = threading.RLock()     # gate check + execution happen atomically
        self.on_tool_attempt = None        # test hook: runs after the agent decides, before the gate

    # --- the gated call path -----------------------------------------------------------
    def call(self, agent, tool, params, ctx):
        params = dict(params or {})
        self.audit.write(f'agent:{agent}', 'tool_attempt', tool=tool, params=params,
                         request_id=ctx.get('request_id'), session_customer=ctx.get('session_customer'))
        if self.on_tool_attempt:
            self.on_tool_attempt(agent, tool, params, ctx)
        with self._lock:
            executed, data = False, None
            try:
                decision = self.gate.check(agent, tool, params, ctx)
                if tool in RECORD_TOOLS:
                    self.store.log_access(f'agent:{agent}', tool, ctx.get('session_customer'),
                                          self._target_customer(tool, params, ctx), decision.allowed)
                if decision.allowed:
                    data = getattr(self, f't_{tool}')(params, ctx)
                    executed = True
                elif decision.outcome == 'escalate' and tool == 'issue_refund':
                    data = self._escalate(params['case_id'], decision.reason, decision.rule)
            except (KeyError, TypeError, ValueError) as e:
                # fail closed: a malformed call never executes
                decision = Decision('deny', 'INPUT', f'Missing or invalid parameter for {tool}: {e}')
                executed, data = False, None
        self.audit.write('policy-gate', 'tool_result', agent=agent, tool=tool, decision=decision.as_dict(),
                         executed=executed, request_id=ctx.get('request_id'))
        return {'ok': executed, 'decision': decision.outcome, 'rule': decision.rule,
                'reason': decision.reason, 'data': data}

    def _target_customer(self, tool, params, ctx):
        """Whose records a tool call is trying to read (for the records-access log)."""
        if params.get('customer_id'):
            return params['customer_id']
        if params.get('order_id'):
            order = self.store.order(params['order_id'])
            return order['customer_id'] if order else None
        if params.get('case_id'):
            case = self.store.case(params['case_id'])
            return case['customer_id'] if case else None
        if params.get('email_id'):
            msg = self.store.one('SELECT customer_id FROM emails WHERE id=?', (params['email_id'],))
            return msg['customer_id'] if msg else None
        return ctx.get('session_customer')

    # --- intake tools ---------------------------------------------------------------------------
    def t_create_case(self, params, ctx):
        form = ctx['form']
        case = self.store.create_case(ctx['session_customer'], form['order_id'], form['amount_cents'],
                                      form['reason'], form.get('channel', 'web'))
        return _public_case(case)

    def t_flag_case(self, params, ctx):
        case = self.store.case(params['case_id'])
        flags = case['flags'] + [params.get('reason', 'flagged')]
        self.store.update_case(case['id'], flags=flags)
        return {'case_id': case['id'], 'flags': flags}

    def t_assign_case(self, params, ctx):
        assignee = params.get('assignee')
        if assignee not in ('refund-agent', 'supervisor-review'):
            assignee = 'supervisor-review'
        status = 'assigned' if assignee == 'refund-agent' else 'awaiting_supervisor'
        self.store.update_case(params['case_id'], assigned_to=assignee, status=status,
                               decision_reason=('Flagged at intake for human review.' if assignee == 'supervisor-review' else None))
        return {'case_id': params['case_id'], 'assigned_to': assignee, 'status': status}

    def t_get_case(self, params, ctx):
        case = self.store.case(params['case_id'])
        out = _public_case(case)
        out['notes'] = [n['note'] for n in self.store.notes_for_case(case['id'])]
        return out

    # --- email tools ------------------------------------------------------------------------------
    def t_send_email(self, params, ctx):
        email_id = self.mail.send(params['to'], params['subject'], params['body'], params.get('case_id'),
                                  ctx.get('session_customer'))
        return {'email_id': email_id, 'to': params['to']}

    def t_read_email(self, params, ctx):
        msg = self.store.one('SELECT * FROM emails WHERE id=?', (params['email_id'],))
        return {k: msg[k] for k in ('id', 'from_addr', 'subject', 'body', 'label', 'created_at')}

    def t_label_email(self, params, ctx):
        self.store.x('UPDATE emails SET label=? WHERE id=?', (params.get('label', ''), params['email_id']))
        return {'email_id': params['email_id'], 'label': params.get('label', '')}

    def t_list_mailbox(self, params, ctx):
        """The customer's mail: what Titanic sent to their address on file, and what they sent Titanic."""
        c = self.store.customer(ctx['session_customer'])
        keep = ('id', 'from_addr', 'to_addr', 'subject', 'body', 'created_at')
        return {'received': [{k: m[k] for k in keep} for m in self.store.emails(direction='out', to_addr=c['email'])],
                'sent': [{k: m[k] for k in keep} for m in self.store.emails(direction='in', customer_id=c['id'])]}

    def t_list_inbox(self, params, ctx):
        rows = self.store.emails(direction='in', customer_id=ctx.get('session_customer'))
        return [{k: r[k] for k in ('id', 'from_addr', 'subject', 'label', 'created_at')} for r in rows]

    # --- records tools ------------------------------------------------------------------------------
    def t_get_customer_profile(self, params, ctx):
        c = self.store.customer(params['customer_id'])
        return {'id': c['id'], 'name': c['name'], 'email': c['email'], 'bank_account': c['bank_account'],
                'balance': config.money(c['balance_cents'])}

    def t_get_order(self, params, ctx):
        o = self.store.order(params['order_id'])
        refunded = self.store.refunded_on_order(o['id'])
        return {'id': o['id'], 'customer_id': o['customer_id'], 'item': o['item'], 'amount': config.money(o['amount_cents']),
                'amount_cents': o['amount_cents'], 'purchased_at': o['purchased_at'], 'already_refunded': config.money(refunded)}

    def t_list_orders(self, params, ctx):
        return [{'id': o['id'], 'item': o['item'], 'amount': config.money(o['amount_cents']),
                 'purchased_at': o['purchased_at'], 'refunded': config.money(o['refunded_cents'])}
                for o in self.store.orders_for(params['customer_id'])]

    def t_search_case_files(self, params, ctx):
        # customer_id always comes from the session, never from the model
        return self.vectordb.search_case_files(params.get('query', ''), ctx['session_customer'])

    def t_save_case_note(self, params, ctx):
        case = self.store.case(params['case_id'])
        self.store.add_note(case['id'], case['customer_id'], 'records-agent', params.get('note', '')[:1000])
        return {'case_id': case['id'], 'saved': True}

    def t_apply_deposit(self, params, ctx):
        dep = self.store.deposit(params['deposit_id'])
        self.payments.deposit(dep)
        c = self.store.customer(dep['customer_id'])
        return {'deposit_id': dep['id'], 'amount': config.money(dep['amount_cents']),
                'new_balance': config.money(c['balance_cents'])}

    def t_get_account_summary(self, params, ctx):
        c = self.store.customer(params['customer_id'])
        return {'customer': {'id': c['id'], 'name': c['name'], 'email': c['email'],
                             'bank_account': c['bank_account'], 'balance': config.money(c['balance_cents']),
                             'balance_cents': c['balance_cents']},
                'orders': self.t_list_orders(params, ctx),
                'cases': [_public_case(k) for k in self.store.cases_for(c['id'])]}

    def t_list_policies(self, params, ctx):
        return self.store.policies()

    def t_upload_policy(self, params, ctx):
        pid = self.store.add_policy(params['title'], params['body'], ctx.get('supervisor', 'supervisor'))
        self.vectordb.add_policy(pid, params['title'], params['body'])
        return {'policy_id': pid, 'title': params['title']}

    # --- refund tools --------------------------------------------------------------------------------
    def t_search_policies(self, params, ctx):
        return self.vectordb.search_policies(params.get('query', ''))

    def t_issue_refund(self, params, ctx):
        case = self.store.case(params['case_id'])
        refund_id = self.payments.refund(case, case['requested_cents'], 'agent', autonomous=True)
        self.store.update_case(case['id'], status='refunded', decision='approved',
                               decision_reason=params.get('reason') or 'Approved under the refund policy.')
        return {'case_id': case['id'], 'refund_id': refund_id, 'amount': config.money(case['requested_cents']),
                'status': 'refunded'}

    def _escalate(self, case_id, reason, rule):
        self.store.update_case(case_id, status='awaiting_supervisor', assigned_to='supervisor-review',
                               decision='escalated', decision_reason=reason)
        self.audit.write('policy-gate', 'escalated_to_supervisor', case_id=case_id, rule=rule, reason=reason)
        return {'case_id': case_id, 'status': 'awaiting_supervisor', 'rule': rule}

    def t_escalate_to_supervisor(self, params, ctx):
        return self._escalate(params['case_id'], params.get('reason', 'Agent asked for human review.'), 'AGENT')

    def t_deny_refund(self, params, ctx):
        self.store.update_case(params['case_id'], status='denied', decision='denied',
                               decision_reason=params.get('reason', 'Not eligible under the refund policy.'))
        return {'case_id': params['case_id'], 'status': 'denied'}

    # --- reporting tools -------------------------------------------------------------------------------
    def t_record_decision_report(self, params, ctx):
        case = self.store.case(params['case_id'])
        outcome = {'refunded': 'Approved', 'denied': 'Denied', 'awaiting_supervisor': 'Waiting for supervisor'}.get(
            case['status'], case['status'])
        self.audit.write('agent:reporting', 'decision_report', case_id=case['id'], outcome=outcome,
                         reason=case['decision_reason'])
        return {'case_id': case['id'], 'outcome': outcome, 'reason': case['decision_reason'],
                'amount': config.money(case['requested_cents'])}

    def t_list_decisions(self, params, ctx):
        cases = self.store.all_cases() if ctx.get('role') == 'supervisor' else self.store.cases_for(ctx['session_customer'])
        return [{'case_id': c['id'], 'customer_id': c['customer_id'], 'status': c['status'],
                 'amount': config.money(c['requested_cents']), 'reason': c['decision_reason']} for c in cases]

    def t_weekly_autonomous_total(self, params, ctx):
        since = (self.store.clock() - config.WEEKLY_WINDOW).isoformat()
        total = self.store.autonomous_total_since(since)
        return {'autonomous_7_day_total': config.money(total), 'limit': config.money(config.WEEKLY_LIMIT_CENTS),
                'remaining': config.money(max(0, config.WEEKLY_LIMIT_CENTS - total))}

    # --- supervisor actions (human, not agent tools) ---------------------------------------------------
    def supervisor_decide(self, case_id, approve, supervisor, note=''):
        with self._lock:
            decision = self.gate.check_supervisor_decision(case_id, approve)
            self.audit.write('policy-gate', 'supervisor_decision_check', case_id=case_id, decision=decision.as_dict())
            if not decision.allowed:
                return {'ok': False, 'reason': decision.reason}
            case = self.store.case(case_id)
            self.store.add_supervisor_decision(case_id, 'approved' if approve else 'denied', supervisor, note)
            self.audit.write(f'supervisor:{supervisor}', 'supervisor_decision', case_id=case_id,
                             decision='approved' if approve else 'denied', note=note)
            if approve:
                refund_id = self.payments.refund(case, case['requested_cents'], f'supervisor:{supervisor}', autonomous=False)
                self.store.update_case(case_id, status='refunded', decision='approved',
                                       decision_reason=f'Approved by supervisor. {note}'.strip())
                return {'ok': True, 'refund_id': refund_id}
            self.store.update_case(case_id, status='denied', decision='denied',
                                   decision_reason=f'Denied by supervisor. {note}'.strip())
            return {'ok': True}

    def set_authority(self, active, supervisor, note=''):
        self.store.set_authority('active' if active else 'revoked', f'supervisor:{supervisor}', note)
        self.audit.write(f'supervisor:{supervisor}', 'authority_restored' if active else 'authority_revoked', note=note)
        if not active:
            # stop queued work: anything assigned to the agent now waits for a human
            for c in self.store.all_cases():
                if c['status'] in ('submitted', 'assigned'):
                    self.store.update_case(c['id'], status='awaiting_supervisor', assigned_to='supervisor-review',
                                           decision_reason='Agent authority was revoked; waiting for a human.')
