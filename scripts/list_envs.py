"""List Isaac Lab environments registered by robot_contact_assembly_tasks."""

from __future__ import annotations

import argparse

parser = argparse.ArgumentParser(description="List robot_contact_assembly Isaac Lab environments.")
parser.add_argument("--keyword", type=str, default=None, help="Optional keyword filter.")
args_cli = parser.parse_args()

import gymnasium as gym
from prettytable import PrettyTable

import robot_contact_assembly_tasks.tasks  # noqa: F401


def main():
    table = PrettyTable(["S. No.", "Task Name", "Entry Point", "Config"])
    table.title = "Robot Contact Assembly Environments"
    table.align["Task Name"] = "l"
    table.align["Entry Point"] = "l"
    table.align["Config"] = "l"

    count = 0
    for task_spec in gym.registry.values():
        if "RCA-" in task_spec.id and (args_cli.keyword is None or args_cli.keyword in task_spec.id):
            table.add_row([count + 1, task_spec.id, task_spec.entry_point, task_spec.kwargs["env_cfg_entry_point"]])
            count += 1

    print(table)


if __name__ == "__main__":
    main()
