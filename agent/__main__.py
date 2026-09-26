"""Executable entry point when running `python3 -m agent` or `python3 agent`."""

import sys
from pathlib import Path

# Ensure root workspace directory is on sys.path when invoked directly as a directory
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agent.cli import main

if __name__ == "__main__":
    main()
