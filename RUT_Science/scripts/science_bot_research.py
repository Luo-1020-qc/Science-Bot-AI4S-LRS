"""Project-anchored research entry; keeps experiment imports out of the Agent."""
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT/"research/strategy_learning/run.py"), run_name="__main__")
