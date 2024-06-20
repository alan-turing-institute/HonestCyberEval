from collections import namedtuple
from copy import deepcopy
from subprocess import CalledProcessError
import yaml
from git import Repo
from api.fs import run_command, RunException

Sanitizer = namedtuple('Sanitizer', ['name', 'error_code'])
Harness = namedtuple('Harness', ['name', 'file_path'])
Source = namedtuple('Source', ['repo', 'ref'])


class ProjectBuildException(RunException):
    pass


class ProjectPatchException(RunException):
    pass


# TODO: complete list of flags and better handling
SANITIZER_COMPILER_FLAGS = {
    "AddressSanitizer": {"-fsanitize=address", "-fno-omit-frame-pointer"},
    "MemorySanitizer": {"-fsanitize=memory", "-fno-omit-frame-pointer"},
}


class ChallengeProject:
    def __init__(self, path):
        self.path = path
        self.__config = self._read_project_yaml()
        self.name = self.__config["cp_name"]

        self.sources = list(self.__config["cp_sources"].keys())
        self.repo = Repo(self.path)
        self.repos = {
            source: Source(
                repo,
                repo.refs[self.__config["cp_sources"][source]["ref"]],
            ) for source in self.sources if (repo := Repo(self.path / "src" / source))
        }

        self.artifacts = {
            source: [
                self.path / artifact for artifact in self.__config["cp_sources"][source]["artifacts"]
            ] for source in self.sources
        }

        self.sanitizers = {
            key: Sanitizer(*(x.strip() for x in value.split(":")))
            for key, value in self.__config["sanitizers"].items()
        }

        self.harnesses = {
            key: Harness(value["name"], self.path / value["source"])
            for key, value in self.__config["harnesses"].items()
        }

        self._set_docker_env()

    @property
    def config(self):
        return deepcopy(self.__config)

    def _set_docker_env(self):
        match self.__config["language"]:
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
            case 'c':
                # TODO: linux kernel uses specific build flags e.g. CONFIG_KFENCE=y, CONFIG_KASAN=y
                # TODO: more control over C config
                cflags = set()
                for sanitizer_name, _ in self.sanitizers.values():
                    cflags |= SANITIZER_COMPILER_FLAGS.get(sanitizer_name)
                with open(self.path / ".env.docker", "w") as env_file:
                    env_file.write(f"CP_BASE_EXTRA_CFLAGS={' '.join(cflags)}")
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
            case 'java':
                # TODO: configure Java compilation
                pass

    def _read_project_yaml(self):
        with open(self.path / "project.yaml", "r") as stream:
            return yaml.safe_load(stream)

    def _run_cp_run_sh(self, *command, **kwargs):
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
        return run_command(self.path / "run.sh", *command, **kwargs)

    def reset_source_repo(self, source):
        self.repos.get(source).repo.git.reset('--hard')

    def build_project(self):
        """Build a project.
        Raises ProjectBuildException, check ProjectBuildException.stderr for output
        """
        result = self._run_cp_run_sh("build")
        if result.stderr:
            raise ProjectBuildException("Build failed", stderr=result.stderr)
        return result

    def patch_and_build_project(self, patch_path, cp_source):
        """Build a project after applying a patch file to the specified source.
        Raises ProjectPatchException if patch cannot be applied, check ProjectPatchException.stderr for output.
        Raises ProjectBuildException, check ProjectBuildException.stderr for output.
        """
        try:
            result = self._run_cp_run_sh("build", patch_path.absolute(), cp_source)
            if result.stderr:
                raise ProjectBuildException("Build failed after patch", stderr=result.stderr)
            return result
        except CalledProcessError as err:
            raise ProjectPatchException("Patching failed", stderr=err.stderr) from err

    def run_harness(self, harness_input_file, harness_id, timeout=60):
        """Runs a specified project test harness and returns the output of the process.
        Check result.stderr for sanitizer output if it exists.
        Can time out when input does not terminate programme.
        Raises:
            subprocess.TimeoutExpired: if harness does not finish in set time
        """
        return self._run_cp_run_sh("run_pov", harness_input_file, self.harnesses[harness_id].name, timeout=timeout)

    def run_harness_and_check_sanitizer(self, harness_input_file, harness_id, sanitizer_id, timeout=60):
        """Runs a specified project test harness and returns whether sanitizer is triggered.
        Can time out when input does not terminate programme.
        Raises:
            subprocess.TimeoutExpired: if harness does not finish in set time
        """
        harness_output = self.run_harness(harness_input_file, harness_id, timeout=timeout)
        sanitizer, error_code = self.sanitizers[sanitizer_id]
        return sanitizer in harness_output.stderr and error_code in harness_output.stderr

    def run_tests(self):
        """Runs a specified project test suite and returns the output of the process.
        Check result.stderr for failed test output if it exists.
        """
        return self._run_cp_run_sh("run_tests")

    def _run_cp_make(self, *command):
        return run_command("make", "-C", self.path, *command)

    def open_project_source_file(self, source, file_path):
        """Opens a file path in the CP.
        source must be one of self.sources
        file_path must be relative to source folder (can be obtained from git history)
        """
        if source not in self.sources:
            return None
        return open(self.path / "src" / source / file_path)
