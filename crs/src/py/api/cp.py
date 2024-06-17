from collections import namedtuple
from copy import deepcopy
from subprocess import CalledProcessError
import yaml
from git import Repo
from api.fs import run_command, docker_login, write_file_to_scratch

Sanitizer = namedtuple('Sanitizer', ['name', 'error_code'])
Harness = namedtuple('Harness', ['name', 'file_path'])
SourceRepo = namedtuple('SourceRepo', ['repo', 'ref'])


class ProjectBuildException(Exception):
    def __init__(self, message, stderr):
        super().__init__(message)
        self.stderr = stderr


class ProjectPatchException(Exception):
    def __init__(self, message, stderr):
        super().__init__(message)
        self.stderr = stderr


class ChallengeProject:
    def __init__(self, path):
        self.path = path
        self.__config = self._read_project_yaml()
        self.name = self.__config["cp_name"]

        self.sources = list(self.__config["cp_sources"].keys())
        self.repo = Repo(self.path)
        self.repos = {
            source: SourceRepo(
                repo,
                repo.refs[self.__config["cp_sources"][source]["ref"]]
            ) for source in self.sources if (repo := Repo(self.path / "src" / source))
        }

        self.sanitizers = {
            key: Sanitizer(*(x.strip() for x in value.split(":")))
            for key, value in self.__config["sanitizers"].items()
        }

        self.harnesses = {
            key: Harness(value["name"], self.path / value["source"])
            for key, value in self.__config["harnesses"].items()
        }

    @property
    def config(self):
        return deepcopy(self.__config)

    def _read_project_yaml(self):
        with open(self.path / "project.yaml", "r") as stream:
            return yaml.safe_load(stream)

    def _run_cp_run_sh(self, *command):
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
        return run_command(self.path / "run.sh", *command)

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

    def run_harness(self, harness_input_file, harness_id):
        """Runs a specified project test harness and returns the output of the process.
        Check result.stderr for sanitizer output if it exists.
        """
        return self._run_cp_run_sh("run_pov", harness_input_file, self.harnesses[harness_id].name)

    def run_harness_and_check_sanitizer(self, harness_input_file, harness_id, sanitizer_id):
        harness_output = self.run_harness(harness_input_file, harness_id)
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

    # temporary code to interact with CP Docker images
    # Organisers are planning to make changes that will create a Docker container for this in local dev
    # https://github.com/aixcc-sc/crs-sandbox/pull/178
    # and images will be present for the CRS to use when running in Stage 2
    # https://github.com/aixcc-sc/crs-sandbox/issues/169
    def _check_docker_image(self):
        image = self.__config["docker_image"]
        try:
            run_command("docker", "image", "inspect", image)
            return True
        except CalledProcessError as err:
            if "No such image" in err.stderr:
                return False
            raise err

    def pull_docker_image(self):
        if not self._check_docker_image():
            docker_login()
            try:
                self._run_cp_make("docker-pull")
            except CalledProcessError as err:
                print("Docker CP image pull error", err.stderr)
                raise err
