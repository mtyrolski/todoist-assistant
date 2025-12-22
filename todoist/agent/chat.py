"""Interactive local chat CLI for the agent."""

import json
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import typer
from loguru import logger

from todoist.agent.context import load_local_agent_context
from todoist.agent.graph import AgentState, build_agent_graph
from todoist.agent.local_llm import DType, Device, LocalChatConfig, TransformersMistral3ChatModel
from todoist.agent.repl_tool import SafePythonReplTool


app = typer.Typer(add_completion=False)

def _parse_device(value: str) -> Device:
    normalized = value.strip().lower()
    if normalized == "cpu":
        return "cpu"
    if normalized == "cuda":
        return "cuda"
    if normalized == "mps":
        return "mps"
    raise typer.BadParameter("device must be one of: cpu, cuda, mps")


def _parse_dtype(value: str) -> DType:
    normalized = value.strip().lower()
    if normalized == "auto":
        return "auto"
    if normalized == "float16":
        return "float16"
    if normalized == "bfloat16":
        return "bfloat16"
    if normalized == "float32":
        return "float32"
    raise typer.BadParameter("dtype must be one of: auto, float16, bfloat16, float32")


@app.command()
def chat(
    model_id: str = typer.Option(
        ...,
        envvar="TODOIST_AGENT_MODEL_ID",
        help="Transformers model id or local path (e.g. mistralai/Ministral-3-3B-Instruct-2512)",
    ),
    cache_path: Path = typer.Option(
        ".",
        envvar="TODOIST_AGENT_CACHE_PATH",
        help="Directory containing local caches like activity.joblib",
    ),
    prefabs_dir: Path = typer.Option(
        "configs/agent_instructions",
        envvar="TODOIST_AGENT_INSTRUCTIONS_DIR",
        help="Directory with YAML instruction prefabs",
    ),
    device: str = typer.Option("cpu", envvar="TODOIST_AGENT_DEVICE", help="cpu/cuda/mps"),
    dtype: str = typer.Option("auto", envvar="TODOIST_AGENT_DTYPE", help="auto/float16/bfloat16/float32"),
    temperature: float = typer.Option(0.2, envvar="TODOIST_AGENT_TEMPERATURE"),
    top_p: float = typer.Option(0.95, envvar="TODOIST_AGENT_TOP_P"),
    max_new_tokens: int = typer.Option(256, envvar="TODOIST_AGENT_MAX_NEW_TOKENS"),
    max_tool_loops: int = typer.Option(8, envvar="TODOIST_AGENT_MAX_TOOL_LOOPS"),
):
    """Chat with the local agent (read-only analysis of local caches)."""

    device_parsed = _parse_device(device)
    dtype_parsed = _parse_dtype(dtype)

    cfg = LocalChatConfig(
        model_id=model_id,
        device=device_parsed,
        dtype=dtype_parsed,
        temperature=temperature,
        top_p=top_p,
        max_new_tokens=max_new_tokens,
    )
    llm = TransformersMistral3ChatModel(cfg)

    local_ctx = load_local_agent_context(cache_path)
    tool_ctx = {
        "events": local_ctx.events,
        "events_df": local_ctx.events_df.copy(),
        "pd": pd,
        "np": np,
    }
    python_tool = SafePythonReplTool(tool_ctx)

    graph = build_agent_graph(llm=llm, python_repl=python_tool, prefabs_dir=prefabs_dir, max_tool_loops=max_tool_loops)
    state: AgentState = {"messages": []}
    logger.info("Local agent ready. Type 'exit' to quit.")
    try:
        while True:
            user_text = input("> ").strip()
            if user_text.lower() in {"exit", "quit", ":q"}:
                break
            if not user_text:
                continue
            logger.info("User message: {}", user_text)
            state["messages"] = list(state.get("messages") or []) + [{"role": "user", "content": user_text}]
            state = cast(AgentState, graph.invoke(state))
            payload = {
                "final_answer": state.get("final_answer"),
                "selected_prefab_ids": state.get("selected_prefab_ids") or [],
                "plan": state.get("plan") or [],
                "tool_steps": int(state.get("tool_steps") or 0),
                "messages": state.get("messages") or [],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    app()
