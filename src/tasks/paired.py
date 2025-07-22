from inspect_ai import Epochs, Task, task
from inspect_ai.scorer import choice, grouped, stderr
from inspect_ai.solver import multiple_choice, prompt_template

from dataset.paired import read_dataset
from metrics.pair_correct import pair_correct
from metrics.pair_prediction import pair_prediction
from solvers.paired import PROMPT, SINGLE_ANSWER_TEMPLATE, SINGLE_ANSWER_TEMPLATE_COT


@task
def pair_wise_vuln(challenge_project: str = "nginx-cp", cot: bool = False) -> Task:
    return Task(
        dataset=read_dataset(challenge_project),
        solver=[
            prompt_template(template=PROMPT),
            multiple_choice(template=SINGLE_ANSWER_TEMPLATE_COT if cot else SINGLE_ANSWER_TEMPLATE),
        ],
        scorer=choice(),
        epochs=Epochs(5),
    )
