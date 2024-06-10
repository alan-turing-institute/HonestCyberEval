from subprocess import CalledProcessError
import yaml
from git import Repo
from api.fs import run_command, docker_login


class ChallengeProject:
    def __init__(self, path):
        self.path = path
        self.config = self._read_project_yaml()
        self.name = self.config["cp_name"]
        self.sources = list(self.config["cp_sources"].keys())
        self.repo = Repo(self.path)
        self.repos = {source: Repo(self.path / "src" / source) for source in self.sources}

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

    def build_project(self):
        """Build a project after applying a patch file to the specified source.
        Check result.stderr for errors in compilation.
        """
        return self._run_cp_run_sh("build")

    def patch_and_build_project(self, patch_path, cp_source):
        """Build a project after applying a patch file to the specified source.
        Throws CalledProcessError if patch cannot be applied.
        Check result.stderr for errors in compilation from a patch that was applied but did not produce correct code.
        """
        return self._run_cp_run_sh("build", patch_path.absolute(), cp_source)

    def run_harness(self, harness_input, harness_id):
        """Runs a specified project test harness and returns the output of the process.
        Check result.stderr for sanitizer output if it exists.
        """
        # TODO: name or binary?
        return self._run_cp_run_sh("run_pov", harness_input, self.config["harnesses"][harness_id]["name"])

    def run_tests(self):
        """Runs a specified project test suite and returns the output of the process.
        Check result.stderr for failed test output if it exists.
        """
        return self._run_cp_run_sh("run_tests")

    def run_cp_make(self, *command):
        return run_command("make", "-C", self.path, *command)

    # temporary code to interact with CP Docker images
    # Organisers are planning to make changes that will create a Docker container for this in local dev
    # https://github.com/aixcc-sc/crs-sandbox/pull/178
    # and images will be present for the CRS to use when running in Stage 2
    # https://github.com/aixcc-sc/crs-sandbox/issues/169
    def _check_docker_image(self):
        image = self.config["docker_image"]
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
                self.run_cp_make("docker-pull")
            except CalledProcessError as err:
                print("Docker CP image pull error", err.stderr)
                raise err

