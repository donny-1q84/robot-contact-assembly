"""Import project task registrations before delegating to Isaac Lab's RSL-RL trainer."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import robot_contact_assembly_tasks.tasks  # noqa: F401


ISAACLAB_TRAIN_SCRIPT = Path("/workspace/IsaacLab/scripts/reinforcement_learning/rsl_rl/train.py")


def main() -> None:
    if not ISAACLAB_TRAIN_SCRIPT.is_file():
        raise FileNotFoundError(
            f"Isaac Lab train.py not found at {ISAACLAB_TRAIN_SCRIPT}. "
            "Run the remote Isaac Lab runtime installation before training."
        )
    sys.argv[0] = str(ISAACLAB_TRAIN_SCRIPT)
    runpy.run_path(str(ISAACLAB_TRAIN_SCRIPT), run_name="__main__")


if __name__ == "__main__":
    main()
