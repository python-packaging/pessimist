import logging
import os
import sys
import tempfile
from pathlib import Path
from subprocess import PIPE, CalledProcessError, check_call, check_output, run
from typing import Dict, List

import click
from honesty.cache import Cache
from honesty.releases import Package, parse_index
from packaging.requirements import Requirement

LOG = logging.getLogger(__name__)


@click.command()
@click.option(
    "--extend", default="", help="Ignore all bounds on these comma-separated packages"
)
@click.option("--fast", is_flag=True, help="Only check extremes")
@click.option(
    "--command", "-c", default="make test", help="Command to run with PATH from venv"
)
@click.option("--verbose", "-v", is_flag=True, help="Show more logging")
@click.argument("target_dir")
def main(target_dir: str, extend: str, fast: bool, command: str, verbose: bool):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING)

    mgr = Manager(
        Path(target_dir).resolve(), command=command, extend=extend.split(","), fast=fast
    )
    if not mgr.solve():
        sys.exit(1)


class Manager:
    def __init__(self, path: Path, command: str, extend: List[str], fast: bool) -> None:
        self.path = path
        self.command = command
        self.extend = extend
        self.fast = fast
        self.reqs: List[Requirement] = []
        self.req_package: Dict[str, Package] = {}
        self.req_versions: Dict[str, List[str]] = {}

        with Cache(fresh_index=True) as cache:
            for filename in path.glob("requirements*.txt"):
                LOG.info("Reading reqs from %s", filename)
                for line in filename.read_text().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    req = Requirement(line)
                    self.reqs.append(req)

                    pkg = parse_index(req.name, cache, use_json=True)
                    self.req_package[req.name] = pkg

                    # TODO this doesn't handle only-pre versions well
                    # TODO some of these don't matter for 'make test', like
                    # mypy, and we'll waste a bunch of time trying versions.
                    if req.name in self.extend or self.extend == "*":
                        versions = list(pkg.releases.keys())
                    else:
                        versions = list(req.specifier.filter(pkg.releases.keys()))
                    self.req_versions[req.name] = versions

                    LOG.info(
                        f"  fetched {req.name}: {len(versions)}/{len(pkg.releases)} allowed"
                    )

    def solve(self) -> bool:
        # Make temporary venv
        with tempfile.TemporaryDirectory() as d:
            sys.stdout.write("set up venv... ")
            sys.stdout.flush()

            check_call([sys.executable, "-m", "venv", d])

            # If there are no matching versions, either it's all-pre or honesty
            # was over-caching.  I'm not sure why that happens yet.

            names = [req.name for req in self.reqs]
            versions = [len(self.req_versions[name]) - 1 for name in names]
            min_idx = [0] * len(names)

            def tolines():
                return [toline(i) for i in range(len(names))]

            def toline(i):
                name = names[i]
                v = versions[i]
                return name if v == -1 else f"{name}=={self.req_versions[name][v]}"

            print("ok")

            LOG.info("Check newest")
            sys.stdout.write("check newest... ")
            sys.stdout.flush()
            result = self.scenario(d, tolines())
            if not result:
                LOG.error("Newest check failed, aborting")
                return False
            print("ok")

            total = 1
            for v in self.req_versions.values():
                total += len(v) - 1

            if not self.fast:
                for i, name in enumerate(names):
                    # try progressively older until we get a failure; skip this for
                    # --fast mode and just try oldest
                    remaining = 1  # "all min" verify
                    for k in range(i, len(names)):
                        remaining += len(self.req_versions[names[k]]) - 1

                    for j in range(len(self.req_versions[name]) - 2, -1, -1):
                        sys.stdout.write(
                            f"check {total-remaining}/{total}...  {name}=={self.req_versions[name][j]} "
                        )
                        sys.stdout.flush()
                        remaining -= 1

                        versions[i] = j
                        LOG.info(f"Check {name}=={self.req_versions[name][j]}")
                        try:
                            result = self.scenario(d, [toline(i)])
                        except CalledProcessError:
                            # TODO some versions can't be installed because
                            # they're wheel-only and don't have a version built
                            # that we're testing on; this considers those to be
                            # failures, but this might need to be
                            # flag-controlled?
                            result = False
                        print("ok" if result else "fail")

                        if not result:
                            if j == len(self.req_versions[name]) - 1:
                                LOG.error("Newest version failed, shouldn't happen")
                            min_idx[i] = j + 1
                            break

                    # Restore to newest, if we changed it...
                    if len(self.req_versions[name]) > 1:
                        versions[i] = len(self.req_versions[name]) - 1
                        self.install(d, toline(i))
                        print()

            # TODO there might be cruft from other versions; how to verify,
            # should we clean, and does that invalidate the more targeted
            # version changes above?
            LOG.info("Check all min")
            versions = min_idx
            result = self.scenario(d, tolines())
            if not result:
                LOG.error("Min check failed, aborting")
                return False

            print("Passing with min:")
            print()
            for i, name in enumerate(names):
                old_req = str(self.reqs[i])
                # TODO if we had a max version, keep that too
                new_req = toline(i).replace("==", ">=")
                if old_req != new_req and "==" not in old_req:
                    print(f"{old_req} -> {new_req}")
                else:
                    print(f"{old_req}")

            return True

    def install(self, venv_dir, line):
        LOG.debug("Install %s", line)
        check_call([f"{venv_dir}/bin/pip", "install", line], stdout=PIPE, stderr=PIPE)

    def scenario(self, venv_dir, lines):
        for line in lines:
            self.install(venv_dir, line)

        env = os.environ.copy()
        env["PATH"] = f"{venv_dir}/bin:{env['PATH']}"
        sys.stdout.flush()

        proc = run(
            self.command,
            shell=True,
            env=env,
            stdout=PIPE,
            stderr=PIPE,
            cwd=self.path,
            encoding="utf-8",
        )
        # TODO: Verify that the versions are as expected; the command might do
        # installs or otherwise change the environment...

        # print(proc.stdout)
        # print(proc.stderr)
        LOG.debug("  Running test: %s", proc.returncode)
        if proc.returncode != 0:
            LOG.debug(proc.stdout)
            LOG.debug(proc.stderr)
        return proc.returncode == 0


if __name__ == "__main__":
    main()
