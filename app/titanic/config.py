"""Titanic settings: refund limits, email allowlist, model, and file paths.

Limits live here in code, not in prompts or retrieved documents, so no text the
model reads can change them. Agents have no tool that can edit these values (R4).
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_DIR = REPO_ROOT / 'data' / 'seed'
DEFAULT_RUNTIME_DIR = REPO_ROOT / 'data' / 'runtime'


def _load_dotenv():
    """Read KEY=VALUE lines from a local .env file (gitignored) without overriding real env vars."""
    path = REPO_ROOT / '.env'
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# --- Refund rules (team decisions, Nov 2026) ---------------------------------
PER_REFUND_LIMIT_CENTS = 100_00      # R1: up to $100.00 per refund without a supervisor (inclusive)
WEEKLY_LIMIT_CENTS = 500_00          # R2: up to $500.00 per rolling 7 days, one total for the agent
WEEKLY_WINDOW = timedelta(days=7)    # rolling window, not calendar week
# Supervisor-approved refunds do NOT count toward the $500 (only autonomous ones do).
REFUND_WINDOW_DAYS = 30

# --- Email rules (R7) ---------------------------------------------------------
SUPPORT_ADDRESS = 'support@titanic.test'              # Titanic's own sending address
INTERNAL_ALLOWLIST = {'supervisor@titanic.test'}      # approved internal recipients

# --- People -------------------------------------------------------------------
SUPERVISOR_PASSCODE = os.environ.get('TITANIC_SUPERVISOR_PASSCODE', 'titanic-supervisor')

# --- Model --------------------------------------------------------------------
MODEL_ID = os.environ.get('TITANIC_MODEL', 'claude-haiku-5-5')
API_KEY_PLACEHOLDER = 'PASTE_YOUR_KEY_HERE'
AGENT_MAX_TURNS = 6                  # cap on tool-use rounds per agent sub-task


def api_key_present():
    key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    return bool(key) and key != API_KEY_PLACEHOLDER


def model_mode():
    """'claude' when a real key is set, otherwise the deterministic offline stand-in."""
    return 'claude' if api_key_present() else 'offline'


def utcnow():
    return datetime.now(timezone.utc)


def money(cents):
    return f'${cents / 100:,.2f}'
