"""Phone normalisation used for duplicate warnings.

This is intentionally conservative: it strips punctuation and whitespace and
keeps a leading ``+``. It does not guess a country code, because assuming one
would turn two different people into a "duplicate" and train the operator to
click through the warning.
"""

import re

_ALLOWED = re.compile(r"[^0-9+]")


def normalise_phone(value: str | None) -> str:
    if not value:
        return ""
    digits = _ALLOWED.sub("", value.strip())
    # Keep at most one leading '+'.
    if digits.startswith("+"):
        return "+" + digits[1:].replace("+", "")
    return digits.replace("+", "")
