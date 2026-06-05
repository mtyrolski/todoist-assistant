#!/usr/bin/env python3
"""Create nested Todoist task trees from inline JSON."""

import argparse
import json
import sys
from pathlib import Path

from loguru import logger

from todoist.features.task_tree_import import (
    create_task_tree_from_json,
    load_task_tree_json,
    normalize_task_tree_payload,
    render_task_tree_plan,
)


EXAMPLE_JSON = """{
  "projectId": "PROJECT_ID",
  "labels": ["ai-import"],
  "tasks": [
    {
      "content": "Ship onboarding cleanup",
      "description": "Outcome: new users can finish setup without support.",
      "labels": ["planning"],
      "children": [
        {
          "content": "Audit current onboarding flow",
          "children": [
            {"content": "Collect failed setup cases"},
            {"content": "List confusing screens"}
          ]
        },
        {"content": "Draft fixes", "dueString": "next week"}
      ]
    }
  ]
}"""

AGENT_PROMPT = f"""Convert the user's pasted text into JSON for this command:

uv run python scripts/create_task_tree.py --execute --json '<JSON>'

Return only one shell command. Use single quotes around the JSON and keep the JSON valid.
Do not invent project IDs; use the projectId I provide. Use concise imperative task titles.
Allowed node fields: content, description, labels, priority, dueString, dueDate, dueDatetime,
duration, durationUnit, deadlineDate, children.

JSON shape:
{EXAMPLE_JSON}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a nested Todoist task tree from inline JSON, a file, or stdin."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--json", help="Inline JSON payload.")
    source.add_argument("--file", type=Path, help="Path to a JSON payload.")
    parser.add_argument(
        "--project-id", help="Override projectId from the JSON payload."
    )
    parser.add_argument(
        "--env",
        default=".env",
        help="Path to the .env file containing TODOIST_API_KEY/API_KEY. Defaults to .env.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually create tasks. Without this flag the script only prints a dry-run plan.",
    )
    parser.add_argument(
        "--print-agent-prompt",
        action="store_true",
        help="Print a prompt you can give to a large LLM to generate this command.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.print_agent_prompt:
        print(AGENT_PROMPT)
        return 0

    try:
        if args.json:
            raw = load_task_tree_json(args.json)
        elif args.file:
            raw = json.loads(args.file.read_text(encoding="utf-8"))
        else:
            raw = json.loads(sys.stdin.read())

        payload = normalize_task_tree_payload(raw, project_id=args.project_id)
        print(render_task_tree_plan(payload))
        if not args.execute:
            print("\nDry-run only. Re-run with --execute to create these tasks.")
            return 0

        created = create_task_tree_from_json(
            raw,
            dotenv_path=args.env,
            project_id=args.project_id,
            dry_run=False,
        )
    except (OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
        logger.error("Task tree import failed: {}", exc)
        return 1

    print(f"\nCreated {len(created)} tasks.")
    for item in created:
        print(f"- {item['id']}: {item['content']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
