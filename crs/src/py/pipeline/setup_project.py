from api.cp import ChallengeProject


def setup_project(project_path):
    project = ChallengeProject(project_path)
    print(f"Building {project.name}", flush=True)
    project.build_project()
    return project
