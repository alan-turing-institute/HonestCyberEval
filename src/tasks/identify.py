from inspect_ai import Task, task
from inspect_ai.scorer import choice
from inspect_ai.solver import multiple_choice, prompt_template

from dataset.identify import read_dataset
from solvers.identify import PROMPT, SINGLE_ANSWER_TEMPLATE, SINGLE_ANSWER_TEMPLATE_COT


@task
def identify_vuln(challenge_project: str = "nginx-cp", cot: bool = False) -> Task:
    return Task(
        dataset=read_dataset(challenge_project),
        solver=[
            prompt_template(template=PROMPT),
            multiple_choice(template=SINGLE_ANSWER_TEMPLATE_COT if cot else SINGLE_ANSWER_TEMPLATE),
        ],
        scorer=choice(),
    )
