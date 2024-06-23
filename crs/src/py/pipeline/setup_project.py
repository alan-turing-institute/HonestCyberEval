from api.cp import ChallengeProject
from logger import logger


def setup_project(project_path):
    project = ChallengeProject(project_path)
    logger.info(f"Resetting project sources, to be safe")
    for source in project.sources:
        project.reset_source_repo(source)
    logger.info(f"Building {project.name}")
    project.build_project()
    return project
