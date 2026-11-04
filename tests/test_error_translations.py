"""K7: every error text the API can send has a Turkish wording in the React app.

The backend keeps English `detail` texts; frontend-v2/src/i18n/locales/tr.ts maps
them under `errors.detail` (exact text) or `errors.detailPrefix` (texts that are
built at runtime, matched by their fixed beginning). This test scans the backend
for those texts and fails when one has no entry, so changing a message without
updating the translation cannot go unnoticed. en.ts must list the same keys.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
LOCALES = ROOT / "frontend-v2" / "src" / "i18n" / "locales"

# Domain exceptions that routes turn into HTTP errors with str(exc) as the detail.
HTTP_MAPPED_EXCEPTIONS = (
    "AlertNotFound",
    "InvalidAlertUpdate",
    "InvalidTransactionFilters",
    "CustomerNotFound",
    "RuleNotFound",
    "InvalidRuleThresholds",
    "DuplicateUsername",
    "InvalidUserInput",
    "UserNotFound",
    "UserRoleNotFound",
    "SelfUpdateForbidden",
)

PATTERNS = (
    re.compile(r'detail=(f?)"([^"]+)"'),
    re.compile(r'^\s*(?:MSG_\w+|\w+_DETAIL|CUSTOMER_CONTEXT_CLOSED)\s*=\s*(f?)"([^"]+)"', re.M),
    re.compile(
        r"raise (?:" + "|".join(HTTP_MAPPED_EXCEPTIONS) + r')\(\s*(f?)"([^"]+)"', re.S
    ),
)


def backend_texts() -> tuple[set[str], set[str]]:
    exact: set[str] = set()
    prefixes: set[str] = set()
    for path in BACKEND.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for pattern in PATTERNS:
            for is_f, text in pattern.findall(source):
                if is_f and "{" in text:
                    prefixes.add(text.split("{", 1)[0])
                else:
                    exact.add(text)
    return exact, prefixes


def locale_maps(name: str) -> tuple[set[str], set[str]]:
    source = (LOCALES / f"{name}.ts").read_text(encoding="utf-8")

    def keys(block: str) -> set[str]:
        match = re.search(r"\n    " + block + r": \{\n(.*?)\n    \},", source, re.S)
        assert match, f"{name}.ts has no errors.{block} block"
        return set(re.findall(r"^\s+'((?:[^'\\]|\\.)*)':", match.group(1), re.M))

    return keys("detail"), keys("detailPrefix")


def test_every_backend_error_text_has_a_turkish_message() -> None:
    exact, prefixes = backend_texts()
    assert len(exact) > 20, "scanner found suspiciously few texts"
    tr_exact, tr_prefixes = locale_maps("tr")
    missing = sorted(
        text
        for text in exact
        if text not in tr_exact and not any(text.startswith(p) for p in tr_prefixes)
    )
    missing_prefixes = sorted(
        prefix
        for prefix in prefixes
        if not any(prefix.startswith(p) for p in tr_prefixes)
    )
    assert missing == [], f"Add to errors.detail in tr.ts: {missing}"
    assert missing_prefixes == [], f"Add to errors.detailPrefix in tr.ts: {missing_prefixes}"


def test_english_locale_lists_the_same_server_texts() -> None:
    assert locale_maps("en") == locale_maps("tr")
