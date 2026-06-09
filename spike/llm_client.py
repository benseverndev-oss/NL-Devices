"""Anthropic-backed `call_model` for the LLMPlanner seam (SPEC-NL-PLANNER.md §3a).

The model's ONLY freedom is to SELECT + name verified blocks via the `emit_plan`
tool. Two things keep it honest, neither trusting the model:
  1. `tool_choice` forces `emit_plan`, and its `block_id` is an enum of catalog
     ids — so the model literally cannot name a part outside the library.
  2. Whatever it emits still passes through the deterministic gate in run().

`anthropic` is imported lazily so the rest of the spike runs with zero deps; this
module only needs the SDK (+ ANTHROPIC_API_KEY) when a real model is actually wired.
"""
from __future__ import annotations

MODEL = "claude-opus-4-8"


def make_call_model(client=None, *, model: str = MODEL, max_tokens: int = 2048):
    """Return a `call_model(system, user, tools) -> dict` matching the LLMPlanner
    seam. The returned dict is the `emit_plan` tool input (`{"instances": [...]}`)."""
    import anthropic  # lazy — only needed when a real model is wired

    client = client or anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    def call_model(system: str, user: str, tools: list[dict]) -> dict:
        tool_name = tools[0]["name"]
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            tool_choice={"type": "tool", "name": tool_name},  # force structured emit
            messages=[{"role": "user", "content": user}],
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input
        raise RuntimeError(
            f"model did not call {tool_name} (stop_reason={resp.stop_reason})")

    return call_model
