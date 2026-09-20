"""Public V5 CLI. Frozen legacy runtimes are not used for new projects."""
from .v5_cli import main

if __name__ == '__main__':
    raise SystemExit(main())
