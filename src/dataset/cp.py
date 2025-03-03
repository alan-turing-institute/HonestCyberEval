from inspect_ai.dataset import MemoryDataset, Sample

from api.cp import ChallengeProjectReadOnly

additional_files = {"nginx": {"cpv12": ["src/nginx/src/http/modules/ngx_http_range_filter_module.c"]}}


def cp_to_dataset(project: ChallengeProjectReadOnly):
    cpvs = project.get_cpv_info()

    return MemoryDataset([
        Sample(
            input=cpv,
            target=project.sanitizer_str[sanitizer_id],
            id=int(cpv.replace("cpv", "")),
            metadata={
                "cpv": cpv,
                "cp_source": cp_source,
                "harness_id": harness_id,
                "sanitizer_id": sanitizer_id,
                "sanitizer": project.sanitizer_str[sanitizer_id],
                "files": files + [project.path / f for f in additional_files.get(project.name, {}).get(cpv, [])],
                "other_patches": other_patches,
                "language": project.language,
            },
        )
        for cpv, cp_source, harness_id, sanitizer_id, files, other_patches in cpvs
    ])
