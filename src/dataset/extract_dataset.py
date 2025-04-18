import asyncio
import json
import sys
from pathlib import Path

from api.fs import get_project
from solvers.setup import setup_project


def generate_paired_dataset(project_name: str):
    project_path = get_project(project_name)
    project_read_only = setup_project(project_path)
    cpvs = project_read_only.get_cpv_info()
    project = asyncio.run(project_read_only.make_writeable_copy("paired"))

    dataset = []
    # patched
    all_patches = cpvs[0][-2] + cpvs[0][-1]
    project.apply_patches(all_patches)
    for cpv, cp_source, harness_id, sanitizer_id, files, patches, other_patches in cpvs:
        code = "\n".join([project.open_project_source_file(cp_source, file_path) for file_path in files])
        dataset.append({
            "input": cpv,
            "id": f"{cpv.replace("cpv", "")}_patched",
            "metadata": {
                "vulnerable": False,
                "cpv": cpv,
                "cp_source": cp_source,
                "harness_id": harness_id,
                "sanitizer_id": sanitizer_id,
                "sanitizer": project.sanitizer_str[sanitizer_id],
                "code": code,
                "files": files,
                "patches": patches,
                "other_patches": other_patches,
                "language": project.language,
            },
        })
    project.reset_all_sources()

    # vulnerable
    for cpv, cp_source, harness_id, sanitizer_id, files, patches, other_patches in cpvs:
        project.apply_patches(other_patches)
        code = "\n".join([project.open_project_source_file(cp_source, file_path) for file_path in files])
        dataset.append({
            "input": cpv,
            "id": f"{cpv.replace("cpv", "")}_vulnerable",
            "metadata": {
                "vulnerable": True,
                "cpv": cpv,
                "cp_source": cp_source,
                "harness_id": harness_id,
                "sanitizer_id": sanitizer_id,
                "sanitizer": project.sanitizer_str[sanitizer_id],
                "code": code,
                "files": files,
                "patches": patches,
                "other_patches": other_patches,
                "language": project.language,
            },
        })
        project.reset_all_sources()

    with open(Path(__file__).parent / "output" / f"{cp.replace("-", "_")}.json", "w") as f:
        f.write(json.dumps(dataset, indent=4))


if __name__ == "__main__":
    try:
        cp = sys.argv[1]
    except IndexError:
        cp = "nginx-cp"
    generate_paired_dataset(cp)
