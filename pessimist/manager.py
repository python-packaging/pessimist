import logging
import os
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from subprocess import PIPE, STDOUT, CalledProcessError, check_call, run
from typing import Dict, List, Optional, Set

from honesty.cache import Cache
from honesty.releases import Package, parse_index
from honesty.version import Version
from packaging.requirements import Requirement

LOG = logging.getLogger(__name__)


class DepError(Exception):
    pass


@dataclass
class Plan:
    title: str
    versions: Dict[str, Version]
    fatal: bool
    name: Optional[str] = None
    version: Optional[Version] = None


@dataclass
class Result:
    item: Plan
    exception: Optional[str]
    output: str


class Manager:
    def __init__(
        self,
        path: Path,
        variable: List[str],
        fixed: List[str],
        command: str,
        extend: List[str],
        fast: bool,
    ) -> None:
        self.path = path
        self.command = command
        self.extend = extend
        self.fast = fast

        self.names: Set[str] = set()
        self.packages: Dict[str, Package] = {}
        self.versions: Dict[str, List[Version]] = {}

        for req_str in [*fixed, *variable]:
            req = Requirement(req_str)
            self.names.add(req.name)

        with Cache(fresh_index=True) as cache:
            # First fetch "fixed" and see how many match:
            # 0: that's an error
            # 1: great!  # >1: warning, and pick the newest (because that's what CI is likely
            # to do; open to other ideas here though)

            for req_str in fixed:
                req = Requirement(req_str)

                pkg = parse_index(req.name, cache, use_json=True)
                self.packages[req.name] = pkg

                versions = list(req.specifier.filter(pkg.releases.keys()))
                if len(versions) == 0:
                    raise DepError("No versions match {req_str!r}; maybe pre-only?")
                if len(versions) > 1:
                    LOG.warning(
                        f"More than one version matched {req_str!r}; picking one arbitrarily."
                    )

                self.versions[req.name] = [versions[-1]]
                LOG.info(
                    f"  [fixed] fetched {req.name}: {len(versions)}/{len(pkg.releases)} allowed; keeping {versions[-1]!r}"
                )

            for req_str in variable:
                req = Requirement(req_str)

                pkg = parse_index(req.name, cache, use_json=True)
                self.packages[req.name] = pkg

                versions = list(req.specifier.filter(pkg.releases.keys()))
                LOG.info(
                    f"  [variable] fetched {req.name}: {len(versions)}/{len(pkg.releases)} allowed"
                )

                if len(versions) == 0:
                    raise DepError("No versions match {req_str!r}; maybe pre-only?")

                if req.name in versions:
                    # Presumably this came from being in 'fixed' too; not being
                    # in 'variable' twice.  If so it will only have one version.
                    if self.versions[req.name][0] not in versions:
                        LOG.warning(
                            f"  [variable] fixed version {self.versions[req.name][0]!r} not in {versions!r} for {req_str!r}"
                        )

                    LOG.info(
                        f"  [variable] widen due to variable: {req_str!r} -> {versions!r}"
                    )

                if fast:
                    if len(versions) == 1:
                        self.versions[req.name] = [versions[0]]
                    else:
                        # zero-length already raised DepError
                        self.versions[req.name] = [versions[0], versions[-1]]
                else:
                    self.versions[req.name] = versions

    def get_max_plan(self) -> Plan:
        return Plan(
            title="max",
            versions={k: v[-1] for k, v in self.versions.items()},
            fatal=True,
        )

    def get_min_plan(self) -> Dict[str, str]:
        return Plan(
            title="min",
            versions={k: v[0] for k, v in self.versions.items()},
            fatal=True,
        )

    def get_intermediate_plans(self) -> List[Plan]:
        # this might look like an unreasonable number, but note that we aren't
        # using all combinations so this is only linear.

        max_vers = self.get_max_plan().versions
        ret: List[Plan] = []
        for k, versions in self.versions.items():
            for v in versions[:-1]:
                vers = max_vers.copy()
                vers[k] = v
                ret.append(
                    Plan(
                        title=f"{k}:{v}", versions=vers, fatal=False, name=k, version=v,
                    )
                )
        return ret

    def solve(self, parallelism: int = 10) -> int:

        queue: Queue[Optional[Plan]] = Queue()
        results: Queue[Result] = Queue()
        should_cancel: bool = False

        def runner():
            with tempfile.TemporaryDirectory() as d:
                check_call([sys.executable, "-m", "venv", d])

                env = os.environ.copy()
                env["PATH"] = f"{d}/bin:{env['PATH']}"
                env["COVERAGE_FILE"] = f"{d}/.coverage"

                while True:
                    item: Optional[Plan] = queue.get(block=True)
                    if item is None:
                        break

                    if should_cancel:
                        break

                    # TODO keep track of what's installed, avoid issuing
                    # duplicate install commands, and detect when an unexpected
                    # version was installed (e.g. from a dep constraint).
                    output: str = ""
                    try:
                        buf = ["python", "-m", "pip", "install"]
                        for k, v in item.versions.items():
                            buf.append(f"{k}=={v}")

                        # TODO: escaping is wrong.
                        output += f"$ {' '.join(buf)}"
                        proc = run(
                            buf,
                            env=env,
                            stdout=PIPE,
                            stderr=STDOUT,
                            cwd=self.path,
                            encoding="utf-8",
                        )
                        output += proc.stdout

                        if proc.returncode != 0:
                            raise Exception("Install failed")

                        output += f"$ {self.command}\n"
                        proc = run(
                            self.command,
                            shell=True,
                            env=env,
                            stdout=PIPE,
                            stderr=STDOUT,
                            cwd=self.path,
                            encoding="utf-8",
                        )
                        output += proc.stdout
                        if proc.returncode != 0:
                            raise Exception("Test failed")

                    except Exception as e:
                        results.put(Result(item, str(e), output))
                    else:
                        results.put(Result(item, None, output))
                    queue.task_done()

        threads = []
        for i in range(parallelism):
            t = threading.Thread(target=runner)
            # t.setDaemon(True)
            t.start()

        # TODO consider these phases?
        outstanding = 0

        queue.put(self.get_max_plan())
        outstanding += 1
        if self.fast:
            queue.put(self.get_min_plan())
            outstanding += 1
        else:
            for plan in self.get_intermediate_plans():
                queue.put(plan)
                outstanding += 1

        min_versions = {}
        rv = 0

        while outstanding and not should_cancel:
            result = results.get(block=True)
            outstanding -= 1
            if result.exception:
                print(f"FAIL {result.item.title}: {result.exception}")
                # for line in result.output.splitlines():
                #     print(f"  {line}")

                if (
                    result.item.name in min_versions
                    and min_versions[result.item.name] < result.item.version
                ):
                    LOG.warning("  Inconsistent result")

                if result.item.fatal:
                    should_cancel = True
                    rv = 1

            else:
                print(f"OK   {result.item.title}")
                if result.item.name:
                    assert result.item.version is not None
                    if result.item.name in min_versions:
                        min_versions[result.item.name] = min(
                            min_versions[result.item.name], result.item.version
                        )
                    else:
                        min_versions[result.item.name] = result.item.version

        if not self.fast:
            print("Final test")
            print("==========")
            print(min_versions)

            queue.put(Plan(title="min", versions=min_versions, fatal=True))
            result = results.get(block=True)
            if result.exception:
                print(f"FAIL {result.item.title}: {result.exception}")
                rv = 2
            else:
                print(f"OK   {result.item.title}")
                for k, v in min_versions.items():
                    if self.versions[k][0] != v:
                        print(f"Suggest narrowing: {k}>={v}")

        for i in range(parallelism):
            queue.put(None)

        for t in threads:
            t.join()

        return rv
