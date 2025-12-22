"""Agentic AI module (LangGraph + local LLM).

This package provides a small, local-first LangGraph agent that can analyze the
already-fetched Todoist activity cache (read-only) via a restricted Python REPL tool.
"""

from todoist.agent.graph import build_agent_graph

__all__ = ["build_agent_graph"]
