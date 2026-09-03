from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def script_text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def auth_guard_position(text: str) -> tuple[int, int]:
    token = re.search(r"const\s+tok\s*=\s*await\s+AUTH\.token\(\)\s*;", text)
    fetch = re.search(r"fetch\([^\n]+/rest/v1/", text)
    guard = re.search(
        r"if\s*\(\s*!tok\s*\)\s*\{\s*showLogin\(\)\s*;\s*"
        r"throw\s+new\s+Error\(\s*[\"']Session expired[^\"']*[\"']\s*\)\s*;\s*\}",
        text,
        re.S,
    )
    if not token:
        raise AssertionError("AUTH.token() call is missing")
    if not fetch:
        raise AssertionError("Supabase REST fetch is missing")
    if not guard:
        raise AssertionError("Missing login guard when AUTH.token() returns null")
    return guard.start(), fetch.start()


class AuthGateTests(unittest.TestCase):
    def test_asset_register_blocks_anonymous_fallback_before_fetch(self):
        guard, fetch = auth_guard_position(script_text("index.html"))
        self.assertLess(guard, fetch)

    def test_irp_portal_blocks_anonymous_fallback_before_fetch(self):
        guard, fetch = auth_guard_position(script_text("irp.html"))
        self.assertLess(guard, fetch)


if __name__ == "__main__":
    unittest.main()
