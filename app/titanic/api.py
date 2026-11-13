"""HTTP API behind the browser UI. Every customer request goes to the orchestrator.

Sign-in is deliberately simple for a synthetic sandbox: customers use their synthetic
customer ID and PIN; the supervisor uses a passcode (TITANIC_SUPERVISOR_PASSCODE).
The session token decides who the customer is; request bodies never do.
"""
import secrets
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config

router = APIRouter()
UI_DIR = Path(__file__).parent / 'ui'
_sessions = {}
_system = None


def system():
    global _system
    if _system is None:
        from .system import TitanicSystem
        _system = TitanicSystem()
    return _system


def to_cents(text, field='amount', max_cents=1_000_000):
    try:
        value = Decimal(str(text).replace('$', '').replace(',', '').strip())
    except InvalidOperation:
        raise HTTPException(400, f'{field} must be a dollar amount like 25.00')
    if not value.is_finite() or value <= 0 or value != value.quantize(Decimal('0.01')):
        raise HTTPException(400, f'{field} must be more than $0 with at most two decimal places')
    cents = int(value * 100)
    if cents > max_cents:
        raise HTTPException(400, f'{field} is too large for this demo')
    return cents


def identity(authorization: str = Header(default='')):
    token = authorization.removeprefix('Bearer ').strip()
    who = _sessions.get(token)
    if not who:
        raise HTTPException(401, 'Please sign in.')
    return who


def customer(who=Depends(identity)):
    if who['role'] != 'customer':
        raise HTTPException(403, 'Customer sign-in required.')
    return who


def supervisor(who=Depends(identity)):
    if who['role'] != 'supervisor':
        raise HTTPException(403, 'Supervisor sign-in required.')
    return who


# --- pages ---------------------------------------------------------------------------------
@router.get('/', include_in_schema=False)
def index():
    return FileResponse(UI_DIR / 'index.html')


@router.get('/customer', include_in_schema=False)
def customer_page():
    return FileResponse(UI_DIR / 'customer.html')


@router.get('/supervisor', include_in_schema=False)
def supervisor_page():
    return FileResponse(UI_DIR / 'supervisor.html')


# --- sign-in & status ---------------------------------------------------------------------
class CustomerLogin(BaseModel):
    customer_id: str
    pin: str


class SupervisorLogin(BaseModel):
    name: str
    passcode: str


@router.post('/api/login')
def login(body: CustomerLogin):
    c = system().store.customer(body.customer_id.strip().upper())
    if not c or not secrets.compare_digest(c['pin'], body.pin.strip()):
        raise HTTPException(401, 'Customer ID or PIN is wrong.')
    token = secrets.token_urlsafe(24)
    _sessions[token] = {'role': 'customer', 'customer_id': c['id'], 'name': c['name']}
    system().audit.write(f'customer:{c["id"]}', 'sign_in')
    return {'token': token, 'customer_id': c['id'], 'name': c['name']}


@router.post('/api/supervisor/login')
def supervisor_login(body: SupervisorLogin):
    if not secrets.compare_digest(body.passcode, config.SUPERVISOR_PASSCODE):
        raise HTTPException(401, 'Passcode is wrong.')
    name = body.name.strip()[:40] or 'supervisor'
    token = secrets.token_urlsafe(24)
    _sessions[token] = {'role': 'supervisor', 'name': name}
    system().audit.write(f'supervisor:{name}', 'sign_in')
    return {'token': token, 'name': name}


@router.get('/api/status')
def status():
    s = system()
    auth = s.store.authority()
    return {'model_mode': s.mode, 'model': config.MODEL_ID if s.mode == 'claude' else 'offline stand-in (no API key set)',
            'authority': auth['status'], 'authority_changed_at': auth['changed_at'],
            'limits': {'per_refund': config.money(config.PER_REFUND_LIMIT_CENTS),
                       'weekly': config.money(config.WEEKLY_LIMIT_CENTS)}}


@router.get('/api/demo-customers')
def demo_customers():
    return system().store.customers()


# --- customer -------------------------------------------------------------------------------
class RefundForm(BaseModel):
    order_id: str
    amount: str
    reason: str


class DepositForm(BaseModel):
    amount: str


class EmailForm(BaseModel):
    subject: str
    body: str


@router.get('/api/me/account')
async def my_account(who=Depends(customer)):
    return await system().orchestrator.handle('account_summary', who)


@router.post('/api/me/refund-requests')
async def submit_refund(body: RefundForm, who=Depends(customer)):
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(400, 'Please describe what went wrong.')
    form = {'order_id': body.order_id.strip().upper(), 'amount_cents': to_cents(body.amount),
            'reason': reason[:2000], 'channel': 'web'}
    return await system().orchestrator.handle('refund_request', who, {'form': form})


@router.post('/api/me/deposits')
async def add_funds(body: DepositForm, who=Depends(customer)):
    dep = system().store.create_deposit(who['customer_id'], to_cents(body.amount, max_cents=100_000))
    return await system().orchestrator.handle('add_funds', who, {'deposit_id': dep['id']})


@router.get('/api/me/mailbox')
async def my_mailbox(who=Depends(customer)):
    """Messages Titanic sent the customer and messages they sent Titanic (through the Customer Email agent)."""
    return await system().orchestrator.handle('mailbox', who)


@router.post('/api/me/emails')
async def email_support(body: EmailForm, who=Depends(customer)):
    s = system()
    c = s.store.customer(who['customer_id'])
    email_id = s.runtime.mail.receive(c['email'], body.subject.strip()[:200], body.body.strip()[:4000], c['id'])
    return await s.orchestrator.handle('inbound_email', who, {'email_id': email_id})


# --- supervisor -------------------------------------------------------------------------------
class DecisionForm(BaseModel):
    approve: bool
    note: str = ''


class AuthorityForm(BaseModel):
    active: bool
    note: str = ''


class PolicyForm(BaseModel):
    title: str
    body: str


@router.get('/api/supervisor/queue')
def queue(who=Depends(supervisor)):
    s = system()
    out = []
    for c in s.store.all_cases():
        if c['status'] == 'awaiting_supervisor':
            order = s.store.order(c['order_id'])
            out.append({**c, 'requested': config.money(c['requested_cents']), 'item': order['item'] if order else '',
                        'order_amount': config.money(order['amount_cents']) if order else '',
                        'notes': [n['note'] for n in s.store.notes_for_case(c['id'])]})
    return out


@router.post('/api/supervisor/cases/{case_id}/decision')
async def decide(case_id: str, body: DecisionForm, who=Depends(supervisor)):
    s = system()
    result = s.runtime.supervisor_decide(case_id, body.approve, who['name'], body.note.strip()[:500])
    if not result['ok']:
        raise HTTPException(400, result['reason'])
    case = s.store.case(case_id)
    follow = await s.orchestrator.handle('supervisor_followup',
                                         {'role': 'supervisor-followup', 'customer_id': case['customer_id'], 'name': who['name']},
                                         {'case_id': case_id})
    return {'decision': 'approved' if body.approve else 'denied', 'case_status': case['status'], 'followup': follow}


@router.post('/api/supervisor/authority')
def authority(body: AuthorityForm, who=Depends(supervisor)):
    system().runtime.set_authority(body.active, who['name'], body.note.strip()[:300])
    return status()


@router.get('/api/supervisor/report')
async def report(who=Depends(supervisor)):
    return await system().orchestrator.handle('weekly_report', who)


@router.get('/api/supervisor/policies')
async def policies(who=Depends(supervisor)):
    return await system().orchestrator.handle('list_policies', who)


@router.post('/api/supervisor/policies')
async def upload_policy(body: PolicyForm, who=Depends(supervisor)):
    if not body.title.strip() or not body.body.strip():
        raise HTTPException(400, 'A policy needs a title and text.')
    return await system().orchestrator.handle('upload_policy', who,
                                              {'policy': {'title': body.title.strip()[:120], 'body': body.body[:20000]}})


@router.get('/api/supervisor/audit')
def audit(limit: int = 150, who=Depends(supervisor)):
    s = system()
    return {'verify': s.audit.verify(), 'entries': list(reversed(s.audit.entries(limit=min(limit, 1000))))}


@router.post('/api/supervisor/reset-demo')
def reset_demo(who=Depends(supervisor)):
    system().reset_demo(who['name'])
    return {'ok': True}
