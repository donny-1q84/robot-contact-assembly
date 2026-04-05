"""Installation script for the robot_contact_assembly_tasks Isaac Lab extension."""

from __future__ import annotations

from pathlib import Path
import tomllib

from setuptools import find_packages, setup


EXTENSION_ROOT = Path(__file__).resolve().parent
EXTENSION_TOML = tomllib.loads((EXTENSION_ROOT / "config" / "extension.toml").read_text())
PACKAGE_META = EXTENSION_TOML["package"]


setup(
    name="robot_contact_assembly_tasks",
    version=PACKAGE_META["version"],
    description=PACKAGE_META["description"],
    author=PACKAGE_META["author"],
    maintainer=PACKAGE_META["maintainer"],
    url=PACKAGE_META["repository"],
    keywords=PACKAGE_META["keywords"],
    packages=find_packages(),
    include_package_data=True,
    install_requires=["psutil"],
    python_requires=">=3.11",
    license="Apache-2.0",
    zip_safe=False,
)
