"""Builds the Titanic architecture diagram from one layout spec.

Outputs (in docs/):
  architecture.drawio  - editable in diagrams.net (app.diagrams.net, free, runs in the browser)
  architecture.svg     - rendered with the same coordinates
Render a PNG from the SVG with headless Chrome (see docs/ARCHITECTURE.md).

Layout follows the professor's example (spec section 3.1): User -> User Input -> Orchestrator Agent with a
Memory block (short-term, long-term, vector DB) on its right, Final Output back to the User, Task Decomposition
below, and specialized agents along the bottom, each with its own LLM and Tools and a Result returning to the
orchestrator. Titanic adds what the description must walk through: the authorization/policy gate between every
agent's tools and the data and services, the human supervisor, the mock services, and the governance audit log.
"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parents[1]
W, H = 1440, 1060

NAVY, GREEN, GREY, RED, AMBER = '#1f3a68', '#2e7d5b', '#5b6b7f', '#b23a48', '#9a6b00'
STYLES = {
    'box': dict(fill='#ffffff', stroke='#1b2a41', font=13, bold=False),
    'key': dict(fill='#ffffff', stroke='#1b2a41', font=13, bold=True),
    'mem': dict(fill='#ffffff', stroke='#1b2a41', font=11, bold=False),
    'small': dict(fill='#ffffff', stroke='#1b2a41', font=10.5, bold=False),
    'gate': dict(fill='#fdf1d3', stroke=AMBER, font=12, bold=False),
    'human': dict(fill='#e3f2ea', stroke=GREEN, font=12, bold=False),
    'svc': dict(fill='#eef1f4', stroke='#1b2a41', font=11.5, bold=False),
    'audit': dict(fill='#f8e3e6', stroke=RED, font=12, bold=False),
}
regions, boxes, edges, labels = [], [], [], []


def region(x, y, w, h, fill, title=None):
    regions.append((x, y, w, h, fill, title))


def box(key, x, y, w, h, text, style='box'):
    boxes.append((key, x, y, w, h, text, style))
    return {'l': (x, y + h / 2), 'r': (x + w, y + h / 2), 't': (x + w / 2, y), 'b': (x + w / 2, y + h),
            'x': x, 'y': y, 'w': w, 'h': h}


def edge(points, color='#1b2a41', start=False, end=True, dashed=False):
    edges.append((points, color, start, end, dashed))


def label(x, y, text, color='#1b2a41', size=10.5, anchor='middle'):
    labels.append((x, y, text, color, size, anchor))


# --- top: user, input, final output -------------------------------------------------------------
user = box('user', 610, 20, 220, 46, 'User\ncustomer or supervisor', 'key')
uin = box('uin', 610, 104, 220, 52, 'User Input\nbrowser UI + API (customer portal,\nsupervisor portal)', 'small')
edge([user['b'], uin['t']])

# --- memory block around the orchestrator -------------------------------------------------------------
region(470, 178, 600, 214, '#e9ecef', 'Memory')
orch = box('orch', 590, 236, 220, 78, 'Orchestrator Agent\nplanner, agent router, response\naggregator (Claude Haiku 5.5)', 'key')
edge([uin['b'], orch['t']])
stm = box('stm', 860, 196, 196, 54, 'Short-term Memory\nper-request state: plan,\nstep results', 'mem')
ltm = box('ltm', 860, 260, 196, 62, 'Long-term Memory\nSQLite: customers, orders, cases,\nrefunds, balances, emails, notes,\nauthority', 'mem')
vdb = box('vdb', 860, 330, 196, 54, 'Vector Database\nChroma: policies,\ncustomer case files', 'mem')
# orchestrator reads and writes all three
edge([(orch['r'][0], 250), (835, 250), (835, stm['l'][1]), stm['l']], start=True)
edge([(orch['r'][0], 280), (860, 280)], start=True)
edge([(orch['r'][0], 304), (840, 304), (840, vdb['l'][1]), vdb['l']], start=True)

fout = box('fout', 300, 236, 170, 52, 'Final Output\nreply in the browser', 'box')
edge([(orch['x'], 262), fout['r']])
edge([fout['l'], (262, 262), (262, 43), user['l']])

# --- task decomposition -------------------------------------------------------------------------------
td = box('td', 640, 416, 120, 44, 'Task\nDecomposition', 'box')
edge([orch['b'], td['t']])

# --- specialized agents -----------------------------------------------------------------------------------
AGENTS = [
    ('intake', 'Case Intake\nAgent', 'Tools: ticket\nsubmission,\nassignment,\ninjection screen'),
    ('email', 'Customer Email\nAgent', 'Tools: send\n(mock email API),\nread/parse inbox,\nlabel'),
    ('records', 'Customer Records\nMgmt Agent', 'Tools: profiles,\norders, balance,\ncase-file RAG,\nnotes, deposits'),
    ('refund', 'Refund Request\nMgmt Agent', 'Tools: policy\nRAG, issue /\ndeny refund,\nescalate'),
    ('reporting', 'Refund Reporting\nAgent', 'Tools: decision\nreports, weekly\nbudget, list\ndecisions'),
]
band_x0, band_w, band_y, band_h = 40, 272, 548, 176
shades = ['#d6e4f7', '#c6daf4', '#b3cdf0', '#a1c1ec', '#8fb5e8']
DEC_Y, RES_Y, TRUNK_X = 500, 520, 612
agent_boxes, tool_boxes = [], []
for i, (key, name, tools) in enumerate(AGENTS):
    bx = band_x0 + i * band_w
    region(bx, band_y, band_w, band_h, shades[i])
    res = box(f'res-{key}', bx + 10, band_y + 22, 72, 44, 'Result', 'box')
    ag = box(f'ag-{key}', bx + 100, band_y + 18, 162, 52, name, 'key')
    llm = box(f'llm-{key}', bx + 100, band_y + 92, 74, 70, 'LLM\nClaude\nHaiku 5.5', 'small')
    tl = box(f'tool-{key}', bx + 180, band_y + 86, 86, 82, tools, 'small')
    edge([ag['l'], res['r']])
    edge([(llm['t'][0], ag['y'] + ag['h']), llm['t']], start=True)
    edge([(tl['t'][0], ag['y'] + ag['h']), tl['t']], start=True)
    # sub-task down from task decomposition (MCP call)
    edge([(ag['t'][0], DEC_Y), ag['t']], color=NAVY)
    # result up to the orchestrator (MCP response)
    edge([res['t'], (res['t'][0], RES_Y)], color=GREEN, end=False)
    agent_boxes.append(ag)
    tool_boxes.append(tl)
edge([td['b'], (td['b'][0], DEC_Y)], color=NAVY, end=False)
edge([(agent_boxes[0]['t'][0], DEC_Y), (agent_boxes[-1]['t'][0], DEC_Y)], color=NAVY, end=False)
first_res_x = band_x0 + 10 + 36
last_res_x = band_x0 + 4 * band_w + 10 + 36
edge([(first_res_x, RES_Y), (last_res_x, RES_Y)], color=GREEN, end=False)
edge([(TRUNK_X, RES_Y), (TRUNK_X, orch['y'] + orch['h'])], color=GREEN)
label(1048, DEC_Y - 7, 'sub-tasks over MCP (signed context)', NAVY, 10.5, 'start')
label(915, RES_Y + 15, 'results back over MCP', GREEN, 10.5, 'start')

# --- policy gate, supervisor, services, governance -------------------------------------------------------
gate = box('gate', 40, 770, 1360, 58,
           'Authorization / Policy Gate (code, not the model): checks every tool call. Allow, deny, or escalate.\n'
           'R1 refund at most $100;  R2 at most $500 per rolling 7 days;  R3 only the case\'s customer;  R4 no permission '
           'changes;\nR5 supervisor decisions stand;  R6 nothing after revocation;  R7 email only the address on file or '
           'supervisor@titanic.test', 'gate')
for tl in tool_boxes:
    edge([tl['b'], (tl['b'][0], gate['y'])], color=AMBER, start=True)
label(943, 760, 'tool call down, allow / deny + result up', AMBER, 10.5, 'middle')

mail = box('mail', 120, 876, 230, 54, 'Mock Email Service\ninbox and sent mail (no real email)', 'svc')
pay = box('pay', 420, 876, 250, 54, 'Mock Payment Service\nissues refunds and deposits by\nupdating the account balance', 'svc')
sup = box('sup', 1100, 870, 250, 70, 'Human Supervisor\n(supervisor portal)\napproves or denies escalations,\nrevokes or restores the agent', 'human')
edge([(mail['t'][0], gate['y'] + gate['h']), mail['t']], start=True)
edge([(pay['t'][0], gate['y'] + gate['h']), pay['t']], start=True)
edge([(1170, gate['y'] + gate['h']), (1170, sup['y'])], color=AMBER)
edge([(1280, sup['y']), (1280, gate['y'] + gate['h'])], color=GREEN)
label(1164, 852, 'escalations', AMBER, 10, 'end')
label(1286, 852, 'approve / deny / revoke', GREEN, 10, 'start')

# data access through the gate: from the gate's right end up into long-term memory and the vector database
DATA_X = 1424
edge([gate['r'], (DATA_X, gate['r'][1]), (DATA_X, ltm['r'][1]), ltm['r']], color=GREY, start=True)
edge([(DATA_X, vdb['r'][1]), vdb['r']], color=GREY)
label(1410, 430, 'record and case-file reads/writes\nthrough the gate, scoped to the\ncase\'s customer', GREY, 10.5, 'end')

audit = box('audit', 40, 982, 1360, 56,
            'Governance layer: append-only, hash-chained audit log. Request, plan, every model call, every tool attempt, '
            'every gate decision\n(allow / deny / escalate + rule), refunds, emails, supervisor decisions, revocations, '
            'policy uploads, red-team results.', 'audit')
edge([(800, gate['y'] + gate['h']), (800, audit['y'])], color=RED)
edge([(sup['b'][0], sup['y'] + sup['h']), (sup['b'][0], audit['y'])], color=RED, start=True)
# orchestrator writes its own entries: down the left edge
edge([(orch['x'], 300), (18, 300), (18, audit['l'][1]), audit['l']], color=RED)
label(26, 430, 'prompts, plans,\nmodel responses', RED, 10.5, 'start')
label(808, 958, 'tool attempts, decisions, refunds, emails', RED, 10.5, 'start')
label(1216, 962, 'decisions in, log read out', RED, 10, 'end')

# legend
label(1180, 26, 'Arrow colors', '#1b2a41', 11, 'start')
for i, (c, t) in enumerate([(NAVY, 'sub-task (MCP)'), (GREEN, 'result / decision'), (AMBER, 'gated tool call'),
                            (GREY, 'data access'), (RED, 'audit write')]):
    edge([(1180, 44 + i * 18), (1214, 44 + i * 18)], color=c)
    label(1222, 48 + i * 18, t, '#1b2a41', 10.5, 'start')


# --- renderers ---------------------------------------------------------------------------------------------------
def svg():
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           f'font-family="Helvetica Neue, Helvetica, Arial, sans-serif">',
           '<defs>' + ''.join(
               f'<marker id="a{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
               f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
               for c in sorted({e[1] for e in edges})) + '</defs>',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    for x, y, w, h, fill, title in regions:
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"/>')
        if title:
            out.append(f'<text x="{x + w - 230}" y="{y + 15}" font-size="12">{escape(title)}</text>')
    for pts, c, start, end, dashed in edges:
        d = ' '.join(f'{x},{y}' for x, y in pts)
        attrs = (f' marker-end="url(#a{c[1:]})"' if end else '') + (f' marker-start="url(#a{c[1:]})"' if start else '')
        dash = ' stroke-dasharray="5 4"' if dashed else ''
        out.append(f'<polyline points="{d}" fill="none" stroke="{c}" stroke-width="1.4"{attrs}{dash}/>')
    for key, x, y, w, h, text, st in boxes:
        s = STYLES[st]
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{s["fill"]}" stroke="{s["stroke"]}" stroke-width="1.2"/>')
        lines = text.split('\n')
        lh = s['font'] * 1.25
        y0 = y + h / 2 - (len(lines) - 1) * lh / 2 + s['font'] * 0.35
        for i, line in enumerate(lines):
            weight = 'bold' if (s['bold'] and i == 0) or (st in ('gate', 'audit', 'human', 'mem', 'svc') and i == 0
                                                         and st != 'gate') else 'normal'
            if st == 'gate' and i == 0:
                weight = 'bold'
            out.append(f'<text x="{x + w / 2}" y="{y0 + i * lh:.1f}" font-size="{s["font"]}" text-anchor="middle" '
                       f'font-weight="{weight}">{escape(line)}</text>')
    for x, y, text, c, size, anchor in labels:
        for i, line in enumerate(text.split('\n')):
            out.append(f'<text x="{x}" y="{y + i * size * 1.25:.1f}" font-size="{size}" fill="{c}" '
                       f'text-anchor="{anchor}">{escape(line)}</text>')
    out.append('</svg>')
    return '\n'.join(out)


def drawio():
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    n = 0

    def nid():
        nonlocal n
        n += 1
        return f'c{n}'
    for x, y, w, h, fill, title in regions:
        cells.append(f'<mxCell id="{nid()}" value="{escape(title or "")}" style="rounded=0;whiteSpace=wrap;html=1;'
                     f'fillColor={fill};strokeColor=none;verticalAlign=top;align=right;spacingRight=170;fontSize=12;" '
                     f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    for pts, c, start, end, dashed in edges:
        (sx, sy), (tx, ty) = pts[0], pts[-1]
        mids = ''.join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in pts[1:-1])
        points = '<Array as="points">' + mids + '</Array>' if mids else ''
        style = (f'edgeStyle=none;html=1;rounded=0;strokeColor={c};strokeWidth=1.4;endArrow={"block" if end else "none"};'
                 f'startArrow={"block" if start else "none"};endFill=1;startFill=1;' + ('dashed=1;' if dashed else ''))
        cells.append(f'<mxCell id="{nid()}" style="{style}" edge="1" parent="1"><mxGeometry relative="1" as="geometry">'
                     f'<mxPoint x="{sx}" y="{sy}" as="sourcePoint"/><mxPoint x="{tx}" y="{ty}" as="targetPoint"/>'
                     f'{points}</mxGeometry></mxCell>')
    for key, x, y, w, h, text, st in boxes:
        s = STYLES[st]
        lines = [escape(l) for l in text.split('\n')]
        lines[0] = f'<b>{lines[0]}</b>' if st != 'box' or s['bold'] else lines[0]
        value = escape('<br>'.join(lines))
        cells.append(f'<mxCell id="{key}" value="{value}" style="rounded=0;whiteSpace=wrap;html=1;fillColor={s["fill"]};'
                     f'strokeColor={s["stroke"]};fontSize={s["font"]};fontFamily=Helvetica;" vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    for x, y, text, c, size, anchor in labels:
        lines = text.split('\n')
        tw = max(len(l) for l in lines) * size * 0.56 + 6
        th = len(lines) * size * 1.3 + 4
        lx = x if anchor == 'start' else (x - tw if anchor == 'end' else x - tw / 2)
        align = {'start': 'left', 'end': 'right', 'middle': 'center'}[anchor]
        value = escape('<br>'.join(escape(l) for l in lines))
        cells.append(f'<mxCell id="{nid()}" value="{value}" style="text;html=1;align={align};verticalAlign=top;'
                     f'fontSize={size};fontColor={c};fontFamily=Helvetica;" vertex="1" parent="1">'
                     f'<mxGeometry x="{lx:.0f}" y="{y - size:.0f}" width="{tw:.0f}" height="{th:.0f}" as="geometry"/></mxCell>')
    return ('<mxfile host="app.diagrams.net"><diagram id="titanic" name="Titanic architecture">'
            f'<mxGraphModel dx="{W}" dy="{H}" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
            f'fold="1" page="1" pageScale="1" pageWidth="{W}" pageHeight="{H}" math="0" shadow="0"><root>'
            + ''.join(cells) + '</root></mxGraphModel></diagram></mxfile>')


if __name__ == '__main__':
    (OUT / 'architecture.svg').write_text(svg())
    (OUT / 'architecture.drawio').write_text(drawio())
    print('wrote', OUT / 'architecture.svg', 'and', OUT / 'architecture.drawio')
