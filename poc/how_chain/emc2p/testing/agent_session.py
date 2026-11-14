"""A single entry point for constructing whichever agent-session driver a
test wants: HeadlessSession (a real provider CLI subprocess -- claude or
copilot) or McpClientSession (litellm + emc2p's own MCP client, for any
other litellm-supported model). See docs/manifest/history.yaml:
project_history.mcp_client_session_added for why both exist.

AgentSession is a typing.Protocol, not a base class -- HeadlessSession and
McpClientSession already duck-type this exact shape (see
McpClientSession's own docstring: "Same public shape as HeadlessSession"),
so neither one had to change its declared base class for this to
type-check them structurally. create_agent_session is the one place that
actually picks a driver from a plain string, mirroring _coerce_provider's
own string -> HeadlessProvider resolution one level down inside
HeadlessSession itself.

Components
----------
- how:
      - value: agent_session.AgentSession
        question: "How is the `AgentSession` class implemented?"
      - value: agent_session.create_agent_session
        question: "How is `create_agent_session` implemented?"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from emc2p.testing.headless_session import HeadlessSession
from emc2p.testing.mcp_client_session import McpClientSession

Driver = Literal["claude", "copilot", "mcp_client"]


@runtime_checkable
class AgentSession(Protocol):
    """The common shape HeadlessSession and McpClientSession already share.

    Structural, not nominal: matching this doesn't require either class
    to inherit from anything new, so both already satisfy it as-is.

    Components
    ----------
    - how:
          - value: AgentSession.__enter__
            question: "How is `__enter__` implemented?"
          - value: AgentSession.__exit__
            question: "How is `__exit__` implemented?"
          - value: AgentSession.send_turn
            question: "How is `send_turn` implemented?"
          - value: AgentSession.usage_summary
            question: "How is `usage_summary` implemented?"
          - value: AgentSession.close
            question: "How is `close` implemented?"
    """

    trace_path: Path

    def __enter__(self) -> "AgentSession":
        """Enter the session as a context manager, connecting whatever the driver needs."""
        ...

    def __exit__(self, *exc_info: object) -> None:
        """Exit the session as a context manager, closing it."""
        ...

    def send_turn(self, prompt: str) -> str:
        """Send one turn to the agent and return its reply."""
        ...

    def usage_summary(self) -> dict:
        """Return this session's accumulated cost/token usage so far."""
        ...

    def close(self) -> None:
        """Shut down the underlying driver and release its resources."""
        ...


def create_agent_session(
    driver: Driver,
    *,
    mcp_config: str | Path,
    allowed_tools: list[str],
    cwd: str | Path,
    model: str,
    extra_env: dict[str, str] | None = None,
    trace_dir: str | Path | None = None,
    turn_timeout: float = 240,
    session_timeout: float = 120,
    provider_options: dict[str, Any] | None = None,
    max_tool_iterations: int | None = None,
    strict_tool_isolation: bool = True,
) -> AgentSession:
    """Construct whichever session class `driver` names.

    Args:
        driver: "claude"/"copilot" spawn a HeadlessSession against that
            provider CLI; "mcp_client" builds a McpClientSession instead
            (litellm-driven, for a model with no headless CLI of its own).
        mcp_config: Path to the `.mcp.json` describing the MCP server(s)
            under test.
        allowed_tools: `mcp__<server>__<tool>`-style glob patterns.
        cwd: Working directory the session runs against.
        model: A model identifier -- meaning depends on `driver` (a
            `claude -p --model` value for "claude", litellm model string
            for "mcp_client"; see each class's own docstring).
        extra_env: Extra environment variables beyond a filtered copy of
            this process's own environment.
        trace_dir: Directory this session's trace file is written under.
            Defaults to `.live_test_traces` under `cwd`.
        turn_timeout: Seconds to wait for a single `send_turn` call.
        session_timeout: Seconds bounding the whole session's wall-clock
            runtime, across every `send_turn` call combined.
        provider_options: Only meaningful for "copilot" today (see
            CopilotHeadlessProvider) -- ignored for "mcp_client".
        max_tool_iterations: Only meaningful for "mcp_client" (passed
            straight through to McpClientSession's own constructor) --
            ignored for "claude"/"copilot", whose HeadlessSession has no
            equivalent per-turn tool-call ceiling.
        strict_tool_isolation: Only meaningful for "claude"/"copilot" (see
            HeadlessSession's own docstring) -- ignored for "mcp_client",
            which never has any built-in tools to strip in the first
            place. Pass False when `allowed_tools` deliberately includes
            a built-in tool (e.g. "Task") that a stripped tool set would
            otherwise remove regardless of `allowed_tools` naming it.

    Returns:
        A HeadlessSession or McpClientSession -- either way, something
        satisfying AgentSession.

    Raises:
        ValueError: If `driver` isn't one of "claude", "copilot", "mcp_client".
    """
    common = dict(
        mcp_config=mcp_config, allowed_tools=allowed_tools, cwd=cwd, model=model,
        extra_env=extra_env, trace_dir=trace_dir,
        turn_timeout=turn_timeout, session_timeout=session_timeout,
    )
    if driver in ("claude", "copilot"):
        return HeadlessSession(
            provider=driver,
            provider_options=provider_options,
            strict_tool_isolation=strict_tool_isolation,
            **common,
        )
    if driver == "mcp_client":
        if max_tool_iterations is not None:
            common["max_tool_iterations"] = max_tool_iterations
        return McpClientSession(**common)
    raise ValueError(f"Unknown driver {driver!r}; expected 'claude', 'copilot', or 'mcp_client'")
