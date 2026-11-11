"""Model access. Real mode calls Claude Haiku 5.5 through the Anthropic API.

The API key is read from the ANTHROPIC_API_KEY environment variable (or a local,
gitignored .env file). It is never hardcoded, logged, or committed. Without a key,
Titanic runs in "offline" mode: each agent follows a fixed, rule-based script that
calls the same tools through the same policy gate, so the app and the gate-level
tests still work. Offline mode is labeled everywhere it appears.
"""
import hashlib
import json

from . import config

FINAL_SCHEMA = {
    'type': 'object',
    'properties': {
        'status': {'type': 'string', 'enum': ['ok', 'needs_human', 'error']},
        'summary': {'type': 'string'},
        'parsed_order_id': {'type': ['string', 'null']},
        'parsed_amount': {'type': ['string', 'null']},
        'parsed_reason': {'type': ['string', 'null']},
        'is_refund_request': {'type': ['boolean', 'null']},
        'suspicious': {'type': ['boolean', 'null']},
    },
    'required': ['status', 'summary', 'parsed_order_id', 'parsed_amount', 'parsed_reason',
                 'is_refund_request', 'suspicious'],
    'additionalProperties': False,
}


def _short(text, n=1500):
    text = text if isinstance(text, str) else json.dumps(text, default=str)
    return text if len(text) <= n else text[:n] + '...[truncated]'


class ClaudeLLM:
    def __init__(self, audit):
        import anthropic  # imported here so offline mode never needs a client
        self.anthropic = anthropic
        self.client = anthropic.AsyncAnthropic()
        self.audit = audit

    def _log(self, actor, system, messages, resp):
        out = []
        for b in resp.content:
            if b.type == 'text':
                out.append({'text': _short(b.text)})
            elif b.type == 'tool_use':
                out.append({'tool_use': b.name, 'input': b.input})
        self.audit.write(actor, 'llm_call', model=config.MODEL_ID,
                         system_prompt_sha256=hashlib.sha256(system.encode()).hexdigest()[:16],
                         last_input=_short(messages[-1]['content']), response=out,
                         stop_reason=resp.stop_reason, request_id=getattr(resp, '_request_id', None),
                         input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens)

    async def _create(self, **kwargs):
        try:
            return await self.client.messages.create(model=config.MODEL_ID, **kwargs)
        except self.anthropic.APIStatusError as e:
            raise RuntimeError(f'Claude API error {e.status_code}: {e.message}') from e
        except self.anthropic.APIConnectionError as e:
            raise RuntimeError('Could not reach the Claude API.') from e

    async def json_call(self, actor, system, user_content, schema, max_tokens=4000):
        messages = [{'role': 'user', 'content': user_content}]
        resp = await self._create(max_tokens=max_tokens, system=system, messages=messages,
                                  output_config={'effort': 'medium', 'format': {'type': 'json_schema', 'schema': schema}})
        self._log(actor, system, messages, resp)
        if resp.stop_reason == 'refusal':
            return None
        text = next((b.text for b in resp.content if b.type == 'text'), '')
        return json.loads(text) if text else None

    async def tool_loop(self, actor, system, user_content, tools, execute, max_turns=config.AGENT_MAX_TURNS):
        """Manual agent loop: Claude picks tools, execute() runs them through the policy gate."""
        messages = [{'role': 'user', 'content': user_content}]
        for _ in range(max_turns):
            resp = await self._create(max_tokens=8000, system=system, tools=tools, messages=messages,
                                      output_config={'effort': 'medium',
                                                     'format': {'type': 'json_schema', 'schema': FINAL_SCHEMA}})
            self._log(actor, system, messages, resp)
            if resp.stop_reason == 'refusal':
                return {'status': 'needs_human', 'summary': 'The model declined this request.'}
            if resp.stop_reason == 'max_tokens':
                return {'status': 'error', 'summary': 'The model ran out of output space.'}
            uses = [b for b in resp.content if b.type == 'tool_use']
            if resp.stop_reason == 'tool_use' and uses:
                messages.append({'role': 'assistant', 'content': resp.content})
                results = []
                for b in uses:
                    out = execute(b.name, b.input)
                    results.append({'type': 'tool_result', 'tool_use_id': b.id,
                                    'content': json.dumps(out, default=str), 'is_error': not out.get('ok')})
                messages.append({'role': 'user', 'content': results})
                continue
            text = next((b.text for b in resp.content if b.type == 'text'), '')
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {'status': 'error', 'summary': 'The model did not return a valid result.'}
        return {'status': 'needs_human', 'summary': f'Stopped after {max_turns} tool rounds.'}
