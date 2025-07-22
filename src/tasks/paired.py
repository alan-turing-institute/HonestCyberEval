from inspect_ai import Epochs, Task, task

from dataset.paired import read_dataset
from solvers.paired import paired_mcq


@task
def pair_wise_vuln(cp: str = "nginx-cp", cot: bool = False) -> Task:
    return Task(
        dataset=read_dataset(cp),
        solver=[
            paired_mcq(cot=cot),
        ],
        epochs=Epochs(5),
    )
