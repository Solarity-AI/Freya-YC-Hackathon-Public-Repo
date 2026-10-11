"""Claude-played customer for chat_e2e (docs/CONTRACTS.md E.4). Owner: agent 4.
Prompt = kit run_cases.persona_for(case, {"identity": case["identity"]}, style)["prompt"] + transcript so far.
Uses claude_agent_sdk directly (independent of builder/llm.py). Output: the customer's next utterance only.

CONTRACT NOTE: model = env HARNESS_PERSONA_MODEL or "claude-haiku-4-5"; no tools, one turn. The persona text is the
system prompt; the user prompt is the transcript (agent = "Caller", customer = "You") plus one instruction.
A failed or timed-out model call raises PersonaError (the runner records it and stops the case; no silent retry).
"""
import asyncio
import os
import re

from builder.paths import import_kit

DEFAULT_MODEL = "claude-haiku-4-5"


class PersonaError(Exception):
    pass


def persona_prompt(case, style=None):
    """Kit persona text for a public-test-set case (same text run_cases sends to the platform)."""
    rc = import_kit("run_cases")
    text = rc.persona_for(case, {"identity": case["identity"]}, style)["prompt"]
    # Local harness only: the persona model otherwise reads "tomorrow" off its own clock (live PUB-12, fix round 1
    # took "tomorrow" as the real-world date and looped on a past date). The call's `now` is the scenario's today.
    now = str(((case or {}).get("variables") or {}).get("now") or "")
    if now:
        try:
            import datetime
            d = datetime.date.fromisoformat(now[:10])
            text += "\n\nIn this call, today is %s, %s (time %s). Relative days ('tomorrow', 'Friday') count from " \
                    "this date." % (d.strftime("%A"), d.isoformat(), now[11:16] or "unknown")
        except ValueError:
            pass
    return text


def render_transcript(transcript):
    lines = []
    for role, text in transcript:
        who = "Caller" if role == "agent" else "You"
        lines.append("%s: %s" % (who, text))
    return "\n".join(lines)


def build_user_prompt(transcript):
    return ("This is the phone call so far:\n\n" + render_transcript(transcript) +
            "\n\nWrite only what you say next on the phone, as plain words. No name prefix, no quotes, "
            "no stage directions.")


def clean(text):
    t = (text or "").strip()
    t = re.sub(r"^\s*(you|customer|me)\s*:\s*", "", t, flags=re.I)
    t = re.sub(r"\[[^\]]*\]|\*[^*]*\*", "", t).strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1].strip()
    return t.splitlines()[0].strip() if t else ""


async def _ask(system_prompt, prompt, model):
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query
    opts = ClaudeAgentOptions(system_prompt=system_prompt, model=model, max_turns=1, tools=[], allowed_tools=[],
                              setting_sources=[])
    parts, result = [], None
    async for msg in query(prompt=prompt, options=opts):
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, TextBlock):
                    parts.append(b.text)
        elif isinstance(msg, ResultMessage):
            result = getattr(msg, "result", None)
    return "".join(parts) or (result or "")


PERSONA_RETRIES = 1


def next_utterance(persona_prompt, transcript, timeout_s=60, model=None):
    """transcript = [(role, text)] with role 'agent' | 'customer' -> next customer line (str)."""
    model = model or os.environ.get("HARNESS_PERSONA_MODEL") or DEFAULT_MODEL
    last = "no attempt"
    for _attempt in range(1 + PERSONA_RETRIES):
        # the persona runs locally, so a retry can never double a platform turn
        try:
            text = asyncio.run(asyncio.wait_for(_ask(persona_prompt, build_user_prompt(transcript), model), timeout_s))
        except Exception as e:                                # noqa: BLE001
            last = "%s: %s" % (type(e).__name__, str(e)[:200])
            continue
        out = clean(text)
        if out:
            return out
        last = "empty persona reply"
    raise PersonaError(last)
