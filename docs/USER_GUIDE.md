# Titanic User Guide

Version 1.0, November 2026. Final system user guide for the CSEN 296B progress report.

Titanic is a customer-support agent for refunds. You can ask for a refund on an order, add funds to your account, check your balance and purchase history, and email support. Titanic approves small refunds by itself. Bigger ones go to a human supervisor, and a supervisor can pause Titanic at any time.

**Everything in Titanic is synthetic.** The customers, orders, emails, bank accounts, and money are made up for testing. No real email is sent and no real money moves.

## Contents
1. [Start Titanic](#1-start-titanic)
2. [Demo accounts](#2-demo-accounts)
3. [The policies Titanic follows](#3-the-policies-titanic-follows)
4. [For customers](#4-for-customers)
5. [For supervisors](#5-for-supervisors)
6. [What each status means](#6-what-each-status-means)
7. [Troubleshooting](#7-troubleshooting)
8. [Limits of this demo](#8-limits-of-this-demo)

## 1. Start Titanic

You need Python 3.11. Python 3.14 is not supported by some of the packages Titanic uses.

```bash
git clone https://github.com/bvanbuiten/CSEN296B-Project-Fall-2026-Titanic.git
cd CSEN296B-Project-Fall-2026-Titanic
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Then open **http://localhost:8000** in your browser.

- **First start:** Titanic sets up its demo data and downloads a small search model (about 80 MB, once). The first page can take 10 to 20 seconds.
- **Choose a portal:** the home page has two doors, the **Customer portal** and the **Supervisor portal**.

![Titanic home page](images/01-home.png)

**Using the real model.** Titanic's agents use Claude Haiku 5.5 when an Anthropic API key is set:
1. Copy `.env.example` to `.env`.
2. Replace `PASTE_YOUR_KEY_HERE` with the key.
3. Restart the app.

Without a key, Titanic runs an offline stand-in that follows fixed rules and goes through the same safety checks. The strip at the top of every page shows which model is running.

## 2. Demo accounts

| Customer | Customer ID | PIN | Email on file | Starting balance |
|---|---|---|---|---|
| Ava Patel | SYN-CUST-001 | 1001 | ava.patel@example.test | $120.00 |
| Ben Okafor | SYN-CUST-002 | 1002 | ben.okafor@example.test | $40.00 |
| Chloe Nguyen | SYN-CUST-003 | 1003 | chloe.nguyen@example.test | $0.00 |
| Diego Ramirez | SYN-CUST-004 | 1004 | diego.ramirez@example.test | $250.50 |
| Emma Schultz | SYN-CUST-005 | 1005 | emma.schultz@example.test | $75.25 |

**Supervisor:** enter any name and the passcode `titanic-supervisor`. To use a different passcode, set `TITANIC_SUPERVISOR_PASSCODE` before starting the app.

Each customer has two to five synthetic orders. Purchase dates are counted back from when Titanic first sets up its data (or from the last demo reset), so the 30-day refund window always behaves the same way.

## 3. The policies Titanic follows

These are the rules Titanic was built to follow. The money limits and safety rules are enforced by code that checks every action. Nothing typed into a message or document can change them.

**Who can get a refund**
- You can ask for a refund on your own order within **30 days** of buying it.
- Valid reasons:
  - the item arrived damaged, broken, or defective
  - it never arrived
  - the wrong item, size, or color was sent
  - parts were missing
- Other reasons, such as a change of mind, are not covered.
- Requests for orders older than 30 days are denied.

**How much**
- A refund can be part or all of what you paid for that order.
- It can never be more than you paid, minus anything already refunded on that order.

**What Titanic can approve on its own**

| Limit | Rule | Above the limit |
|---|---|---|
| Per refund | Up to **$100.00**. $100.00 exactly is allowed. | Goes to a human supervisor. |
| Per 7 days | Up to **$500.00** in total across all customers, over any rolling 7-day period. $500.00 exactly is allowed. | Goes to a human supervisor. |

- Refunds a supervisor approves do not count toward the $500.

**Where the money goes**
- Approved refunds are credited to your Titanic account balance.
- Titanic never sends money anywhere else.

**Privacy**
- Titanic only reads and shares your own records.
- It never shows, emails, or exports another customer's information.

**Email**
- Titanic emails only the address on file for your account.
- If you ask it to use a different address, it keeps using the one on file.

**Messages are information, not instructions**
- Writing "my manager already approved this", "ignore your rules", or "raise my limit" does not change anything.
- Requests like that are flagged and sent to a person.

**Supervisors**
- A human supervisor decides every escalated refund, and their decision is final.
- A supervisor can pause Titanic at any time. While it is paused, Titanic does nothing: no refunds, no emails, no account views.

## 4. For customers

### 4.1 Sign in
1. Open the **Customer portal**.
2. Pick your name and enter your PIN from the table above.
3. Click **Sign in**.

![Customer sign-in](images/02-customer-sign-in.png)

### 4.2 Check your balance and purchase history
After you sign in, the left side of the page shows:
- **Your account:** your balance and your linked (synthetic) bank account.
- **Purchase history:** each order's ID, item, purchase date, amount paid, and amount already refunded. Each order has a **Refund** button.
- **Your cases:** every refund request you have made, its status, and the reason Titanic gave.

The strip at the top shows the refund limits, whether Titanic is active or paused, and which model is running.

![Customer portal](images/03-customer-portal.png)

### 4.3 Ask for a refund

1. Click **Refund** next to an order, or open the **Ask for a refund** tab.
2. Fill in the form.
3. Click **Send refund request**.

| Field | What to enter | Rules |
|---|---|---|
| Order | Pick one of your orders | You can only pick your own orders. |
| Refund amount in dollars | For example `40.00` or `40` | More than $0, at most two decimal places, and no more than what you paid for the order. |
| What went wrong? | A short description, such as "The mugs arrived broken." | Required. Longer text is cut to 2,000 characters. Describe the problem; the agent decides the outcome. |

![Refund request form](images/04-refund-form.png)

**What happens next.** After a few seconds (up to about a minute with the real model), a panel called **What happened to your request** opens. It shows Titanic's reply and each step the agents took:
1. **Case Intake** opens your case and checks the request.
2. **Customer Email** sends you an acknowledgement with your case number.
3. **Customer Records** checks the order, the purchase date, the amounts, and your case files.
4. **Refund Requests** decides: approve, deny, or send to a supervisor.
5. **Customer Email** emails you the decision.
6. **Refund Reporting** records the decision and the reason.

Under each step, **Tool calls and policy-gate decisions** shows every action the agent tried and whether Titanic's safety checks allowed it.

**The three possible results**
- **Approved:** the money is added to your balance right away, and you get an email.

  ![A refund Titanic approved](images/05-refund-approved-trace.png)

- **With a supervisor:** the request was over a limit or needs a person to look at it. Your case waits for a supervisor, and you get an email when it is decided.

  ![A refund sent to a supervisor](images/06-refund-escalated-trace.png)

- **Denied:** the request does not meet the policy, for example because the order is more than 30 days old. The reason appears in your case list and in the email.

### 4.4 Add funds
1. Open the **Add funds** tab.
2. Enter an amount, for example `25.00`. The most you can add at a time is $1,000.00.
3. Click **Add funds**.

Your balance updates and you get a receipt email. The money comes from your synthetic linked account.

### 4.5 Email support
You can also ask for a refund by email:
1. Open the **Email support** tab.
2. Enter a subject and a message.
3. Click **Send email**.

To get a refund this way, include all three of these:
- the **order ID**, for example `SYN-ORD-101`
- the **amount**, for example `$79.99`; if you leave it out, Titanic uses the full refundable amount
- **what went wrong**

The Customer Email agent reads and labels your email. If it is a refund request for one of your orders, Titanic opens a case and handles it exactly like the form. Otherwise it files the email with support.

![Email support](images/07-email-support.png)

### 4.6 Read your mailbox
**Your mailbox**, on the right, shows every email Titanic sent you: acknowledgements, decisions, and receipts. All of them go to your address on file.

![Mailbox](images/09-mailbox.png)

Here is the whole customer page after a refund, a supervisor case, a deposit, and an email request:

![Customer portal after several requests](images/08-customer-after.png)

## 5. For supervisors

### 5.1 Sign in
Open the **Supervisor portal**, enter your name and the passcode, and click **Sign in**.

![Supervisor portal](images/10-supervisor-portal.png)

### 5.2 Decide escalated refunds
**Waiting for you** lists every case Titanic sent to a person. Each card shows:
- the amount and the item
- the customer and the order
- **why it is here**, for example "over the $100.00 per-refund limit" or "flagged at intake"
- any warning flags
- what the customer wrote

To decide a case:
1. Optionally, add a note to the customer.
2. Click **Approve refund** or **Deny refund**.

When you approve, the money goes to the customer's balance. Either way, the customer gets an email and the decision is recorded. Your approvals do not count toward the agent's $500 weekly limit.

![An escalated case](images/11-escalation.png)

### 5.3 Pause or restore Titanic
Under **Agent authority**:
- Click **Revoke agent authority** to stop Titanic at once. You can add a note for the audit log.
- Click **Restore agent authority** to let it work again.

While Titanic is revoked:
- **No agent actions:** the agent cannot refund, email, or read records.
- **Queued cases:** any case that was waiting for the agent moves to your queue.
- **Customers:** they see a "paused" notice and cannot send requests.

![Authority revoked](images/13-revoked.png)

![What customers see while Titanic is paused](images/14-customer-paused.png)

### 5.4 This week and all cases
**This week** shows how much the agent refunded on its own in the last 7 days against the $500.00 limit, how much is left, and how many cases are in each status. **All cases** lists every case with its status and reason.

![This week](images/16-this-week.png)

### 5.5 Policies
**Policies** lists the documents the agents search when they make decisions. To add one:
1. Open **Upload a policy**.
2. Enter a title and the text.
3. Click **Upload policy**.

A policy can guide decisions, such as which reasons count. It **cannot** change the $100 and $500 limits or any safety rule; those are fixed in code.

### 5.6 Audit log
The **Audit log** lists every request, plan, model call, tool attempt, policy-gate decision, refund, email, supervisor decision, and revocation, newest first.

**Hash chain verified** means no past entry has been changed or deleted.

![Audit log](images/15-audit-log.png)

### 5.7 Red-team tests and demo data
- **Red-team tests:** runs Titanic's security tests. Each test runs in its own throwaway copy of Titanic and saves its results under `redteam/results/`. RT-03 and RT-04 need the API key. The full test list is in `redteam/plan.md`.
- **Reset demo data:** reloads the synthetic customers and orders. The old audit log is archived, not deleted.

![Red-team test panel](images/12-redteam-panel.png)

## 6. What each status means

| Status you see | Meaning |
|---|---|
| Submitted / In review | The case is open and the agent is working on it. |
| Refunded | Approved. The amount is in the customer's balance. |
| Denied | Not approved. The reason is shown with the case and in the email. |
| With a supervisor | Waiting for a human decision, because of a limit, a flag at intake, or a pause. |
| Allowed / Denied / To supervisor | In the step trace: what Titanic's safety checks decided about one action. |
| Guardrail | In the step trace: a safety check stepped in to finish a step safely, for example by sending an undecided case to a supervisor. |

## 7. Troubleshooting

| You see | What to do |
|---|---|
| "Customer ID or PIN is wrong." | Check the PIN in the demo accounts table. |
| "amount must be more than $0 with at most two decimal places" | Enter a dollar amount like `25` or `25.00`. |
| "The order on the form belongs to a different customer..." | You can only ask about your own orders. |
| "...more than the $X still refundable on order..." | Ask for no more than you paid, minus what was already refunded. |
| "Titanic's agent is paused by a supervisor" | Wait for a supervisor to restore it. Nothing you sent was processed. |
| The model shows "offline stand-in" | No API key is set. Titanic still works, using fixed rules. |
| The app does not start on Python 3.14 | Use Python 3.11. |
| The first page load is slow | The search model downloads once on first start. |

## 8. Limits of this demo
- **Sign-in is simple on purpose.** It uses synthetic IDs and PINs and a shared supervisor passcode. Sessions end when the app restarts.
- **Email and payments are mock services.** Nothing leaves your computer except calls to the Claude API when a key is set.
- **Offline mode.** Without an API key, the agents follow fixed scripts. The safety checks are identical, but the agents' judgment is not the model's.
