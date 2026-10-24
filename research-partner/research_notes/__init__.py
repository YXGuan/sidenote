"""A local, file-based companion for Hypothesis."""

from pathlib import Path
import sys

# Keep optional Python dependencies in this workspace, including for launchd.
_dependencies = Path(__file__).resolve().parents[1] / ".local-tools/python"
if _dependencies.is_dir():
    # An isolated runtime must prefer its own Python-version-specific wheels.
    if sys.prefix == sys.base_prefix:
        sys.path.insert(0, str(_dependencies))
    else:
        sys.path.append(str(_dependencies))

__version__ = "0.1.0"
