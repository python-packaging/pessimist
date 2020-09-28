import logging
import sys
from pathlib import Path
from typing import List

import click

from .manager import Manager
from .util import get_metadata, get_requirements


@click.command()
@click.option(
    "--extend", default="", help="Ignore all bounds on these comma-separated packages"
)
@click.option("--fast", is_flag=True, help="Only check extremes")
@click.option(
    "--command", "-c", default="make test", help="Command to run with PATH from venv"
)
@click.option(
    "--parallelism", "-p", default="10", help="Number of concurrent runners", type=int
)
@click.option("--verbose", "-v", is_flag=True, help="Show more logging")
@click.argument("target_dir")
def main(
    target_dir: str,
    extend: str,
    fast: bool,
    command: str,
    parallelism: int,
    verbose: bool,
) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING)

    variable: List[str] = get_metadata(Path(target_dir)).get_all("Requires-Dist", [])
    fixed = get_requirements(Path(target_dir))

    print("Summary")
    print("=======")
    print("Variable", variable)
    print("Fixed", fixed)
    print()

    mgr = Manager(
        Path(target_dir).resolve(),
        variable=variable,
        fixed=fixed,
        command=command,
        extend=extend.split(","),
        fast=fast,
    )

    print("Versions")
    print("========")
    for k, v in mgr.versions.items():
        print(k, [str(x) for x in v])
    print()

    sys.exit(mgr.solve(parallelism))


if __name__ == "__main__":
    main()
