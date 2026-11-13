// Shared helpers for the Titanic pages.
const AGENT_NAMES = {
  intake: 'Case Intake', email: 'Customer Email', records: 'Customer Records',
  refund: 'Refund Requests', reporting: 'Refund Reporting',
};

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function cents(money) {
  return Math.round(parseFloat(String(money).replace(/[$,]/g, '')) * 100) || 0;
}

function dollars(c) {
  return '$' + (c / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function shortDate(iso) {
  return new Date(iso.slice(0, 10) + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

async function api(path, { method = 'GET', body, tokenKey } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  const token = tokenKey && sessionStorage.getItem(tokenKey);
  if (token) headers.Authorization = 'Bearer ' + token;
  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

function statusChip(status) {
  const map = {
    refunded: ['ok', 'Refunded'], approved: ['ok', 'Approved'], denied: ['no', 'Denied'],
    awaiting_supervisor: ['wait', 'With a supervisor'], assigned: ['', 'In review'], submitted: ['', 'Submitted'],
    ok: ['ok', 'Done'], needs_human: ['wait', 'Needs a person'], error: ['no', 'Problem'], skipped: ['', 'Skipped'],
    allow: ['ok', 'Allowed'], deny: ['no', 'Denied'], escalate: ['wait', 'To supervisor'],
  };
  const [cls, text] = map[status] || ['', status];
  return `<span class="chip ${cls}">${esc(text)}</span>`;
}

// The ribbon under the navigation bar: live limits, agent authority, and model.
async function loadRail() {
  const el = document.getElementById('rail');
  if (!el) return;
  try {
    const s = await api('/api/status');
    const active = s.authority === 'active';
    el.classList.toggle('is-revoked', !active);
    el.innerHTML = `Titanic approves refunds up to <strong>${esc(s.limits.per_refund)}</strong> on its own, and no more than
      <strong>${esc(s.limits.weekly)}</strong> in any 7 days. Agent authority:
      <span class="state ${active ? 'active' : 'revoked'}">${active ? 'Active' : 'Revoked by a supervisor'}</span>.
      Model: ${esc(s.model)}.`;
  } catch (e) { el.textContent = ''; }
}

const OUTCOMES = {
  refunded: ['ok', 'Refund approved.'],
  awaiting_supervisor: ['wait', 'Sent to a supervisor.'],
  denied: ['no', 'Refund denied.'],
  assigned: ['', 'Request received.'],
  submitted: ['', 'Request received.'],
};

function renderTrace(target, result) {
  const [cls, headline] = result.paused ? ['no', 'Nothing was processed.']
    : (result.case ? (OUTCOMES[result.case.status] || ['', 'Request received.']) : ['ok', 'Done.']);
  const steps = (result.steps || []).map(s => {
    const calls = s.tool_calls || [];
    const items = calls.map(t => `<li><code>${esc(t.tool)}</code> ${statusChip(t.decision)}${t.rule ? ' rule ' + esc(t.rule) : ''}${t.executed ? '' : ' (did not run)'}</li>`).join('');
    return `<li>
      <div><span class="agent">${esc(AGENT_NAMES[s.agent] || s.agent)}</span>${statusChip(s.status)}</div>
      <div class="summary">${esc(s.summary)}</div>
      ${s.guardrail ? `<div class="guard">Guardrail: ${esc(s.guardrail)}</div>` : ''}
      ${items ? `<details><summary>Tool calls and policy-gate decisions (${calls.length})</summary><ul>${items}</ul></details>` : ''}
    </li>`;
  }).join('');
  target.innerHTML = `
    <h2 class="outcome ${cls}">${esc(headline)}</h2>
    <p class="reply">${esc(result.message)}</p>
    <span class="mode">Handled by ${result.model_mode === 'claude' ? 'Claude Haiku 5.5' : 'the offline stand-in model'}</span>
    ${steps ? `<h3>What each agent did</h3><ol class="steps">${steps}</ol>` : ''}`;
  target.classList.remove('hidden');
  const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  target.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' });
}
