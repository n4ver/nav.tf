import sys
from pathlib import Path

# Allow tests to import modules from src/
SRC_PATH = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_PATH))
