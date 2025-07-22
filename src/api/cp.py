import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import yaml
from git import Reference, Repo

from config import CP_ROOT


@dataclass
class Harness:
    name: str
    file_path: Path


@dataclass
class Source:
    repo: Repo
    ref: Reference


additional_files = {
    "nginx": {"cpv12": ["src/nginx/src/http/modules/ngx_http_range_filter_module.c"]}
}


class ChallengeProject:
    def __init__(self, path: Path):
        self.path = path
        self.__config = self._read_project_yaml()
        self.name = self.__config["cp_name"]
        self.language = self.__config["language"].title()

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
            source: [
                self.path / artifact
                for artifact in self.__config["cp_sources"][source]["artifacts"]
            ]
            for source in self.sources
        }

        self.harnesses = {
            key: Harness(value["name"], self.path / value["source"])
            for key, value in self.__config["harnesses"].items()
        }

    @property
    def config(self):
        return deepcopy(self.__config)

    @property
    def sanitizers(self):
        return deepcopy(self.__config["sanitizers"])

    def _read_project_yaml(self):
        project_yaml_path = self.path / "project.yaml"
        return yaml.safe_load(project_yaml_path.read_text())

    def open_project_source_file(self, source: str, file_path: Path) -> str:
        """Opens a file path in the CP.
        source must be one of `self.sources`
        file_path must be relative to source folder (can be obtained from git history)
        """
        return (self.path / "src" / source / file_path).read_text()

    def get_cpv_info(self):
        cpv_dir = self.path / ".internal_only"
        if not cpv_dir.exists():
            cpv_dir = self.path / "exemplar_only"
        if not cpv_dir.exists():
            raise Exception("Vulnerabilities not defined")

        patches = []
        for cpv in cpv_dir.iterdir():
            patches_dir = cpv / "patches"
            for other_source in self.sources:
                patch_path = patches_dir / other_source / "good_patch.diff"
                if patch_path.exists():
                    patches.append((other_source, str(patch_path.resolve())))
                    break

        cpv_info = []
        for cpv in cpv_dir.iterdir():
            info_file = cpv / "pov_pou_info"
            if info_file.exists():
                pov_harness, sanitizer = info_file.read_text().strip().split(",")
                sanitizer_id = list(self.sanitizers.keys())[
                    list(self.sanitizers.values()).index(sanitizer.strip())
                ]

                harness_index = [
                    harness["name"] for harness in self.config["harnesses"].values()
                ].index(pov_harness.strip())
                harness_id = list(self.config["harnesses"].keys())[harness_index]
            else:
                if len(self.sanitizers) == 1:
                    sanitizer_id = next(self.sanitizers.keys())
                elif "1" in cpv.name:
                    sanitizer_id = "id_1"
                elif "2" in cpv.name:
                    sanitizer_id = "id_2"
                else:
                    raise Exception("sanitizer_id not determined")

                if len(self.harnesses) == 1:
                    harness_id = next(iter(self.harnesses))
                else:
                    raise Exception("harness_id not determined")

            sanitizer = self.sanitizers[sanitizer_id]
            harness_name = self.harnesses[harness_id].name
            harness_code = self.harnesses[harness_id].file_path.read_text()

            files = []
            patches_dir = cpv_dir / cpv.name / "patches"
            cp_source = ""
            for source in self.sources:
                patch_path = patches_dir / source / "good_patch.diff"
                if patch_path.exists():
                    patch = patch_path.read_text()
                    files.extend(re.findall("(?<=\\+\\+\\+ b/).*(?=\n)", patch))
                    cp_source = source
                    break
            files.extend(
                [
                    str(self.path / f)
                    for f in additional_files.get(self.name, {}).get(cpv.name, [])
                ]
            )

            this_patches = [
                (cp_source, patch_path)
                for cp_source, patch_path in patches
                if cpv.name in patch_path
            ]
            other_patches = [
                (cp_source, patch_path)
                for cp_source, patch_path in patches
                if cpv.name not in patch_path
            ]
            cpv_info.append(
                (
                    cpv.name,
                    cp_source,
                    harness_name,
                    harness_code,
                    sanitizer,
                    files,
                    this_patches,
                    other_patches,
                )
            )
        return cpv_info

    def reset_source_repo(self, source):
        git_repo = self.repos[source].repo
        ref = self.repos[source].ref
        git_repo.git.restore(".")
        git_repo.git.switch("--detach", ref)

    def reset_all_sources(self):
        for source in self.sources:
            self.reset_source_repo(source)

    def apply_patches(self, patches: list[tuple[str, Path]]):
        for cp_source, patch_path in patches:
            git_repo = self.repos[cp_source].repo
            git_repo.git.execute(["git", "apply", patch_path])


def get_project(challenge_project) -> ChallengeProject:
    for item in CP_ROOT.iterdir():
        if item.is_dir() and item.name == challenge_project:
            return ChallengeProject(item)
    raise Exception(f"Could not find project {challenge_project}")
