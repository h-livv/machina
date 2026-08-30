from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="machina", description="Local machine control plane: telemetry, hardware, jobs, models")
    parser.add_argument("--once", action="store_true", help="Print one telemetry snapshot as JSON and exit")
    parser.add_argument("--dump", action="store_true", help="Alias for --once")
    args = parser.parse_args(argv)

    if args.once or args.dump:
        from machina.telemetry import Sampler
        import time

        sampler = Sampler()
        sampler.snapshot()
        time.sleep(0.35)
        json.dump(sampler.snapshot().to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    from machina.ui.main_window import run_app

    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
