import asyncio
import math
from copy import deepcopy
from pathlib import Path
from shutil import copy
from subprocess import CalledProcessError
from typing import NamedTuple

import aiorwlock
import yaml
from aioshutil import copytree
from git import Reference, Repo

from config import AIXCC_CP_ROOT, AIXCC_CRS_SCRATCH_SPACE
from logger import logger

from .data_types import Patch
from .fs import PatchException, RunException, run_command

Sanitizer = NamedTuple("Sanitizer", [("name", str), ("error_code", str)])
Harness = NamedTuple("Harness", [("name", str), ("file_path", Path)])
Source = NamedTuple("Source", [("repo", Repo), ("ref", Reference)])


class ProjectBuildException(RunException):
    message = "Build failed"


class ProjectBuildAfterPatchException(PatchException):
    message = "Build failed after applying patch"


class ProjectPatchException(PatchException):
    message = "Patching failed using:"


class ChallengeProjectReadOnly:
    writeable_copy_async: asyncio.Task["ChallengeProject"]

    def __init__(self, path: Path, input_path: Path, patch_path: Path):
        self.path = path
        self.input_path = input_path
        self.patch_path = patch_path
        self.__config = self._read_project_yaml()
        self.name = self.__config["cp_name"]
        self.language = self.__config["language"].title()
        self._make_main_writeable_copy()

        self.sources = list(self.__config["cp_sources"].keys())
        self.repo = Repo(self.path)
        self.repos = {
            source: Source(
                repo,
                repo.references[self.__config["cp_sources"][source]["ref"]],
            )
            for source in self.sources
            if (repo := Repo(self.path / "src" / source))
        }

        self.artifacts = {
            source: [self.path / artifact for artifact in self.__config["cp_sources"][source]["artifacts"]]
            for source in self.sources
        }

        self.sanitizers = {
            key: Sanitizer(*(x.strip() for x in value.split(":"))) for key, value in self.__config["sanitizers"].items()
        }

        self.harnesses = {
            key: Harness(value["name"], self.path / value["source"])
            for key, value in self.__config["harnesses"].items()
        }

    @property
    def config(self):
        return deepcopy(self.__config)

    @property
    def sanitizer_str(self) -> str:
        return self.__config["sanitizers"]

    def _make_main_writeable_copy(self):
        logger.info(f"Copying {self.name} to scratch")
        self.writeable_copy_async = asyncio.create_task(self.make_writeable_copy("", initial_build=True))

    def _read_project_yaml(self):
        project_yaml_path = self.path / "project.yaml"
        return yaml.safe_load(project_yaml_path.read_text())

    def open_project_source_file(self, source: str, file_path: Path) -> str:
        """Opens a file path in the CP.
        source must be one of `self.sources`
        file_path must be relative to source folder (can be obtained from git history)
        """
        return (self.path / "src" / source / file_path).read_text()

    async def make_writeable_copy(self, name_extra: str, initial_build: bool = False) -> "ChallengeProject":
        destination_path = AIXCC_CRS_SCRATCH_SPACE / AIXCC_CP_ROOT.name / f"{self.path.name}{name_extra}"
        await copytree(self.path, destination_path, copy_function=copy, dirs_exist_ok=True)
        return ChallengeProject(
            destination_path,
            self.input_path,
            self.patch_path,
            initial_build=initial_build,
        )


class ChallengeProject(ChallengeProjectReadOnly):
    def __init__(
        self,
        path: Path,
        input_path: Path,
        patch_path: Path,
        initial_build: bool = False,
    ):
        super().__init__(path, input_path, patch_path)
        self._build_lock = aiorwlock.RWLock()
        self.writeable_copy_async = asyncio.create_task(self._return_self())
        self._test_duration = None
        self._harness_duration = None
        if initial_build:
            logger.info(f"Building {self.name}")
            self.initial_build = asyncio.create_task(self.build_project())
            # self._initial_test_run = asyncio.create_task(self._run_tests_for_timing())
        else:
            self.initial_build = self.writeable_copy_async
        # self._set_docker_env()

    @property
    def build_lock(self):
        return self._build_lock.writer_lock

    @property
    def run_lock(self):
        return self._build_lock.reader_lock

    async def _return_self(self) -> "ChallengeProject":
        return self

    def _make_main_writeable_copy(self, build=True):
        pass

    def _set_docker_env(self):
        # not used currently
        docker_env_path = self.path / ".env.docker"
        output = {}
        match self.language:
            # `CC` - C compiler binary
            # `CXX` - C++ compiler binary
            # `CCC` - C++ compiler binary
            # `CP_BASE_CFLAGS` - C compiler flags for CP base target (default: CP-specific)
            # `CP_BASE_EXTRA_CFLAGS`- Supplemental C compiler flags CP base target (default: empty)
            # `CP_BASE_CXXFLAGS` - C++ compiler flags for CP base target (default: CP-specific)
            # `CP_BASE_EXTRA_CXXFLAGS`- Supplemental C++ compiler flags CP base target (default: empty)
            # `CP_BASE_LDFLAGS` - Linker flags for CP base target (default: CP-specific)
            # `CP_BASE_EXTRA_LDFLAGS` - Supplemental linker flags for CP base target (default: empy)
            # `CP_BASE_LIBS` - Libraries to be linked for CP base target (default: CP-specific)
            # `CP_BASE_EXTRA_LIBS` - Supplemental libraries to be linked for CP base target (default: empty)
            # `CP_HARNESS_CFLAGS` - C compiler flags for CP harness(es) target (default: CP-specific)
            # `CP_HARNESS_EXTRA_CFLAGS`- Supplemental C compiler flags for CP harness(es) target (default: empty)
            # `CP_HARNESS_CXXFLAGS` - C++ compiler flags for CP harness(es) target (default: CP-specific)
            # `CP_HARNESS_EXTRA_CXXFLAGS`- Supplemental C++ compiler flags for CP harness(es) target (default: empty)
            # `CP_HARNESS_LDFLAGS` - Linker flags for CP harness(es) target (default: CP-specific)
            # `CP_HARNESS_EXTRA_LDFLAGS` - Supplemental linker flags for CP harness(es) target (default: empty)
            # `CP_HARNESS_LIBS` - Libraries to be linked for CP harness(es) target (default: CP-specific)
            # `CP_HARNESS_EXTRA_LIBS` - Supplemental libraries to be linked for CP harness(es) target (default: empty)
            case "C":
                ...
            # `JAVA_HOME` - The root directory of installed Java Development Kit (default: `/opt/java/openjdk`)
            # `MAVEN_HOME` - The root directory of the installed Maven package (default: `/usr/share/maven`)
            # `MVN` - Maven's `mvn` binary (default: `/usr/bin/mvn`)
            # `CP_BASE_MAVEN_ARGS` - Arguments passed to Maven before the CLI for building the CP base target (default: CP-specific)
            # `CP_BASE_EXTRA_MAVEN_ARGS` - Supplemental arguments passed to Maven before the CLI for building the CP base target (default: empty)
            # `CP_BASE_MAVEN_OPTS` - Parameters passed to JVM running Maven for building the CP base target (default: CP-specific)
            # `CP_BASE_EXTRA_MAVEN_OPTS` - Supplemental parameters passed to JVM running Maven for building the CP base target (default: empty)
            # `CP_HARNESS_MAVEN_ARGS` - Arguments passed to Maven before the CLI for building the CP harness(es) (default: CP-specific)
            # `CP_HARNESS_EXTRA_MAVEN_ARGS` - Supplemental arguments passed to Maven before the CLI for building the CP harness(es) (default: empty)
            # `CP_HARNESS_MAVEN_OPTS` - Parameters passed to JVM running Maven for building the CP harness(es) (default: CP-specific)
            # `CP_HARNESS_EXTRA_MAVEN_OPTS` - Supplemental parameters passed to JVM running Maven for building the CP harness(es) (default: empty)
            case "Java":
                ...
        if output:
            docker_env_path.write_text("\n".join([f"{k}={v}" for k, v in output.items()]))

    async def _run_cp_run_sh(self, *command, **kwargs):
        """
        Copied from run.sh:
        A helper script for CP interactions.

        Usage: build|run_pov|run_test|custom

        Subcommands:
            build [<patch_file> <source>]       Build the CP (an optional patch file for a given source repo can be supplied)
            run_pov <blob_file> <harness_name>  Run the binary data blob against specified harness
            run_tests                           Run functionality tests
            custom <arbitrary cmd ...>          Run an arbitrary command in the docker container
        """

        # TODO: check if -x flag is more convenient
        async with self.run_lock:
            return await run_command(self.path / "run.sh", *command, **kwargs)

    async def _run_tests_for_timing(self):
        await self.initial_build
        _, _, _, duration = await self._run_cp_run_sh("run_tests", timed=True)
        self._test_duration = math.ceil(duration) * 2  # double it just to be sure

    def reset_source_repo(self, source):
        git_repo, ref = self.repos[source]
        git_repo.git.restore(".")
        git_repo.git.switch("--detach", ref)

    async def _build(self, *args):
        async with self.build_lock:
            try:
                process, _, stderr, _ = await self._run_cp_run_sh("build", *args)
                if stderr:
                    raise ProjectBuildException(stderr=stderr)
                return process
            except CalledProcessError as err:
                raise ProjectBuildException(stderr=err.stderr) from err

    async def build_project(self):
        """Build a project.
        Raises ProjectBuildException, check ProjectBuildException.stderr for output
        """
        return await self._build()

    async def patch_and_build_project(self, patch: Patch, cp_source):
        """Build a project after applying a patch file to the specified source.
        Raises ProjectBuildAfterPatchException if patch cannot be applied, check ProjectBuildAfterPatchException.stderr
          for output.
        Raises ProjectBuildException, check ProjectBuildException.stderr for output.
        """
        # ensure we are on the tip and no other patches are lingering before patching
        async with self.build_lock:
            self.reset_source_repo(cp_source)
            return await self._build(str(patch.diff_file.absolute()), cp_source)

    async def run_harness(self, harness_input_file, harness_id, timeout=False):
        """Runs a specified project test harness and returns the output of the process.
        Check result.stderr for sanitizer output if it exists.
        Can time out when input does not terminate programme.
        Raises:
            asyncio.TimeoutError: if harness does not finish in set time
        """
        if timeout:
            extra_kwargs = {"timeout": max(5, self._harness_duration or 0)}
        elif not self._harness_duration:
            extra_kwargs = {"timed": True}
        else:
            extra_kwargs = {}
        process, stdout, stderr, duration = await self._run_cp_run_sh(
            "run_pov",
            harness_input_file,
            self.harnesses[harness_id].name,
            **extra_kwargs,
        )
        if self._harness_duration is None:
            self._harness_duration = math.ceil(duration) * 2
        return process, stdout, stderr

    async def run_harness_and_check_sanitizer(
        self, harness_input_file, harness_id, sanitizer_id, timeout=False
    ) -> tuple[bool, str]:
        """Runs a specified project test harness and returns whether sanitizer is triggered.
        Can time out when input does not terminate programme.
        Raises:
            asyncio.TimeoutError: if harness does not finish in set time
        """
        _, _, stderr = await self.run_harness(harness_input_file, harness_id, timeout=timeout)
        sanitizer, error_code = self.sanitizers[sanitizer_id]
        return sanitizer in stderr and error_code in stderr, stderr

    async def run_tests(self):
        """Runs a specified project test suite and returns the output of the process.
        Check stderr for failed test output if it exists.
        """
        _, _, stderr, _ = await self._run_cp_run_sh("run_tests", timeout=self._test_duration)

        return stderr

    async def _run_cp_make(self, *command):
        return await run_command("make", "-C", self.path, *command)
