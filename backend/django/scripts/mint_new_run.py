"""Smoke-test bootstrap for the Phase 3 mint script.

Identical in shape to `mint_run.py`: set Django up, then execute
`scripts/mint_new.py`, writing to `MINT_OUT` (or argv[1]) when one is given.

    python backend/django/scripts/mint_new_run.py [output-file]

The environment variable exists because a path containing spaces survives an
environment variable in every shell, while passing it as a quoted argument from
PowerShell does not.
"""

import os
import sys
from pathlib import Path

DJANGO_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = DJANGO_DIR / "scripts"
if str(DJANGO_DIR) not in sys.path:
    sys.path.insert(0, str(DJANGO_DIR))
# So `mint_new.py` can `from mint_common import ...`: it is executed as a script
# from this directory, not imported as part of a package.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

namespace: dict = {"__name__": "__main__"}
code = compile(
    (SCRIPTS_DIR / "mint_new.py").read_text(encoding="utf-8"),
    "mint_new.py",
    "exec",
)

output_name = os.environ.get("MINT_OUT") or (sys.argv[1] if len(sys.argv) > 1 else "")

if output_name:
    output_path = Path(output_name)
    with open(output_path, "w", encoding="utf-8") as output:
        original_stdout = sys.stdout
        sys.stdout = output
        try:
            exec(code, namespace)
        finally:
            sys.stdout = original_stdout
    print(f"wrote {output_path}")
else:
    exec(code, namespace)
