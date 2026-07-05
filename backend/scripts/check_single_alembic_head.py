from pathlib import Path
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory


def main() -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))

    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()

    if len(heads) != 1:
        joined_heads = ", ".join(heads) if heads else "<none>"
        print(
            f"Alembic head check failed: expected exactly 1 head, found {len(heads)} ({joined_heads}).",
            file=sys.stderr,
        )
        return 1

    print(f"Alembic head check passed: {heads[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
