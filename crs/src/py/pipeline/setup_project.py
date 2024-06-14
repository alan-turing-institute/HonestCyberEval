from api.cp import ChallengeProject


def setup_project(project_path):
    project = ChallengeProject(project_path)
    project.pull_docker_image()
    print(f"Building {project.name}", flush=True)
    project.build_project()
    return project
