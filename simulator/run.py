"""`python simulator/run.py` - the same thing as `python -m simulator`.

This exists because both spellings are natural, and the second one works without
any package-install step: the path fix-up below puts the directory that contains
`simulator/` on `sys.path`, so `from simulator.cli import main` resolves whether
the script was started from the repository root or from inside `simulator/`.

    python simulator/run.py --ecg --duration 30
    python -m simulator --ecg --duration 30        (from the repository root)
"""

from __future__ import annotations

import sys
from pathlib import Path

# .../simulator/run.py -> .../simulator -> .../   (the directory holding the package)
PACKAGE_PARENT = Path(__file__).resolve().parent.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from simulator.cli import main  # noqa: E402  (after the path fix-up, on purpose)


if __name__ == "__main__":
    raise SystemExit(main())
