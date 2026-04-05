"""Import project task registrations before delegating to Isaac Lab's RSL-RL player."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import robot_contact_assembly_tasks.tasks  # noqa: F401


ISAACLAB_PLAY_SCRIPT = Path("/workspace/IsaacLab/scripts/reinforcement_learning/rsl_rl/play.py")


def main() -> None:
    if not ISAACLAB_PLAY_SCRIPT.is_file():
        raise FileNotFoundError(
            f"Isaac Lab play.py not found at {ISAACLAB_PLAY_SCRIPT}. "
            "Run the remote Isaac Lab runtime installation before playback."
        )
    sys.argv[0] = str(ISAACLAB_PLAY_SCRIPT)
    runpy.run_path(str(ISAACLAB_PLAY_SCRIPT), run_name="__main__")


if __name__ == "__main__":
    main()
