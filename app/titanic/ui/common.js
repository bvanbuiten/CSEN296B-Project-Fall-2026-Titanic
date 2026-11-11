// Shared helpers for the Titanic pages.
const AGENT_NAMES = {
  intake: 'Case Intake', email: 'Customer Email', records: 'Customer Records',
  refund: 'Refund Requests', reporting: 'Refund Reporting',
};

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
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

async function loadRail() {
  const el = document.getElementById('rail');
  if (!el) return;
  try {
    const s = await api('/api/status');
    el.innerHTML = `
      <div><span>Agent approves on its own up to</span><strong>${esc(s.limits.per_refund)} per refund</strong></div>
      <div><span>and at most</span><strong>${esc(s.limits.weekly)} per 7 days</strong></div>
      <div class="${s.authority === 'active' ? 'active' : 'revoked'}"><span>Agent authority</span>
        <strong>${s.authority === 'active' ? 'Active' : 'Revoked by a supervisor'}</strong></div>
      <div><span>Model</span><strong>${esc(s.model)}</strong></div>`;
  } catch (e) { el.textContent = ''; }
}

function renderTrace(target, result) {
  const steps = (result.steps || []).map(s => {
    const calls = (s.tool_calls || []).map(t =>
      `<li>${esc(t.tool)} ${statusChip(t.decision)}${t.rule ? ' rule ' + esc(t.rule) : ''}${t.executed ? '' : ' (did not run)'}</li>`).join('');
    return `<li>
      <div><span class="agent">${esc(AGENT_NAMES[s.agent] || s.agent)}</span> ${statusChip(s.status)}</div>
      <div>${esc(s.summary)}</div>
      ${s.guardrail ? `<div class="guard">Guardrail: ${esc(s.guardrail)}</div>` : ''}
      ${calls ? `<details><summary>Tool calls and policy-gate decisions</summary><ul>${calls}</ul></details>` : ''}
    </li>`;
  }).join('');
  target.innerHTML = `
    <div class="panel-head"><h2>What happened to your request</h2>
      <span class="mode">${result.model_mode === 'claude' ? 'Claude Haiku 5.5' : 'Offline stand-in model'}</span></div>
    <p class="reply">${esc(result.message)}</p>
    ${steps ? `<ol>${steps}</ol>` : ''}`;
  target.classList.remove('hidden');
}
