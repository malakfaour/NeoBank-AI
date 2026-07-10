"""
DEVATTECH-121 / SP3-702: fail CI when app/core/config.py's Settings fields
and the repo-root .env.example fall out of sync.

This exact bug already happened once (per ENGINEERING_RULES.md: a test set
SMTP_USER while config read SMTP_USERNAME and it was silently ignored), and
as of this script's first run it caught a live instance: REQUIRE_ACTION_TOKEN
is declared in Settings but missing from .env.example.

Run from backend/:
    python scripts/check_env_example.py

Exits 1 (and prints exactly what's out of sync) if:
  - a Settings field has no corresponding line in .env.example, or
  - .env.example has a key that isn't a Settings field (stale/typo'd entry)
"""
import ast
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
CONFIG_PATH = BACKEND_DIR / "app" / "core" / "config.py"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"


def get_settings_fields() -> set[str]:
    """
    Parse config.py's Settings class via AST and return every field name
    (annotated class attribute). Using AST instead of importing the module
    directly, since importing would require a real DATABASE_URL/JWT_SECRET
    etc. to be set -- this script must run cleanly in CI with no .env at all.
    """
    tree = ast.parse(CONFIG_PATH.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            fields = set()
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if item.target.id == "model_config":
                        continue
                    fields.add(item.target.id)
            return fields

    raise RuntimeError(f"Could not find a 'Settings' class in {CONFIG_PATH}")


def get_env_example_keys() -> set[str]:
    """Parse .env.example for KEY=... lines, ignoring comments/blank lines."""
    keys = set()
    pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
    for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = pattern.match(stripped)
        if match:
            keys.add(match.group(1))
    return keys


def main() -> int:
    settings_fields = get_settings_fields()
    env_example_keys = get_env_example_keys()

    missing_from_env_example = sorted(settings_fields - env_example_keys)
    stale_in_env_example = sorted(env_example_keys - settings_fields)

    if not missing_from_env_example and not stale_in_env_example:
        print(f"OK: {len(settings_fields)} Settings fields all present in .env.example")
        return 0

    if missing_from_env_example:
        print(f"FAIL: {len(missing_from_env_example)} Settings field(s) missing from .env.example:")
        for name in missing_from_env_example:
            print(f"  - {name}")
        print("  Add these to .env.example (see ENGINEERING_RULES.md #8).")

    if stale_in_env_example:
        print(f"FAIL: {len(stale_in_env_example)} .env.example key(s) not in Settings (typo or removed field):")
        for name in stale_in_env_example:
            print(f"  - {name}")

    return 1


if __name__ == "__main__":
    sys.exit(main())