import sys
from pathlib import Path

# The scripts (extract.py, transcribe.py, compile.py) live at the project
# root and aren't an installable package: add the root to the import path so
# tests can `import extract`, `import transcribe`, `import compile` directly.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
