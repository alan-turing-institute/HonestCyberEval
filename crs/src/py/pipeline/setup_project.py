from api.cp import ChallengeProject


def setup_project(project_path):
    project = ChallengeProject(project_path)
    print(f"Resetting project sources, to be safe", flush=True)
    for source in project.sources:
        project.reset_source_repo(source)
    print(f"Building {project.name}", flush=True)
    project.build_project()
    return project
