"""Smoke-test bootstrap: set Django up, then run scripts/mint.py.

    python scripts/mint_run.py [output-file]

Output goes to stdout, and to `output-file` when one is given (or to `MINT_OUT`
when that environment variable is set). The environment variable exists because
a path containing spaces survives an environment variable in every shell, while
passing it as a quoted argument from PowerShell does not. This file exists so the
smoke test can be driven without an interactive shell.
"""

import os
import sys
from pathlib import Path

DJANGO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DJANGO_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

namespace: dict = {"__name__": "__main__"}
code = compile(
    (DJANGO_DIR / "scripts" / "mint.py").read_text(encoding="utf-8"),
    "mint.py",
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
