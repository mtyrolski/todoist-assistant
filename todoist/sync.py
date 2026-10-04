"""Explicit local data sync command for source and packaged installations."""

import argparse

from loguru import logger

from todoist.core.runtime_env import resolve_runtime_env_path
from todoist.database.base import Database
from todoist.features.data_sync import backfill_activity_history, sync_recent_activity


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh the local Todoist activity cache")
    parser.add_argument("--history", action="store_true", help="Backfill older activity")
    args = parser.parse_args()
    db = Database(str(resolve_runtime_env_path()))
    try:
        recent = sync_recent_activity(db)
        logger.info("Activity sync complete: {} new, {} cached", len(recent.new_events), len(recent.events))
        if args.history:
            history = backfill_activity_history(db)
            logger.info("History sync complete: {} new, {} cached", len(history.new_events), len(history.events))
    finally:
        db.reset()


if __name__ == "__main__":
    main()
