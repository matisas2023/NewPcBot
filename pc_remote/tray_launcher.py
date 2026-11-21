"""Absolute launcher used by Windows Run; independent of the caller's cwd."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pc_remote.desktop import main

if __name__ == '__main__':
    main()
