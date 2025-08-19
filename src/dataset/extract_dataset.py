import json
import sys
from pathlib import Path

from api.cp import get_project


def generate_dataset(project_name: str):
    project = get_project(project_name)
    project.reset_all_sources()
    cpvs = project.get_cpv_info()

    dataset = []

    base = dict()

    for (
        cpv,
        cp_source,
        harness_name,
        harness_code,
        sanitizer,
        code_files,
        patches,
        other_patches,
    ) in cpvs:
        project.apply_patches(other_patches)
        files = {
            str(
                (Path("patches") / src / Path(patch_path).parts[-4]).with_suffix(
                    ".diff"
                )
            ): patch_path
            for src, patch_path in other_patches
        }
        sources = list(set([src for src, _ in other_patches]))
        code = "\n".join(
            [
                project.open_project_source_file(cp_source, file_path)
                for file_path in code_files
            ]
        )
        base[cpv] = {
            "input": cpv,
            "id": f"{int(cpv.replace('_', '').replace('cpv', '')):02d}",
            "target": sanitizer,
            "files": files,
            "metadata": {
                "language": project.language,
                "cpv": cpv,
                "cp_source": cp_source,
                "harness_name": harness_name,
                "harness_code": harness_code,
                "sanitizer": sanitizer,
                "code_files": code_files,
                "patches": patches,
                "other_patches": other_patches,
                "vulnerable": True,
                "sources": sources,
                "code": code,
            },
        }
        project.reset_all_sources()

    # patched
    all_patches = cpvs[0][-2] + cpvs[0][-1]
    project.apply_patches(all_patches)
    for (
        cpv,
        cp_source,
        _,
        _,
        _,
        code_files,
        _,
        _,
    ) in cpvs:
        code = "\n".join(
            [
                project.open_project_source_file(cp_source, file_path)
                for file_path in code_files
            ]
        )
        base_vuln = base[cpv]
        dataset.append(
            {
                **base_vuln,
                "metadata": {
                    **base_vuln["metadata"],
                    "fixed_code": code,
                },
            }
        )
    project.reset_all_sources()

    with open(
        Path(__file__).parent / "output" / f"{cp.replace('-', '_')}.json", "w"
    ) as f:
        f.write(json.dumps(dataset, indent=4, sort_keys=True))


if __name__ == "__main__":
    try:
        cp = sys.argv[1]
    except IndexError:
        cp = "nginx-cp"
    generate_dataset(cp)
