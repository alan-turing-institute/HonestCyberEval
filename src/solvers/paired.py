import re

from inspect_ai._util.answer import answer_index
from inspect_ai.agent import Agent, AgentState, agent, run
from inspect_ai.model import ChatMessageSystem, ChatMessageUser, ModelOutput, get_model
from inspect_ai.scorer import CORRECT, INCORRECT, NOANSWER, Score
from inspect_ai.solver import Choices, Generate, Solver, TaskState, solver
from inspect_ai.solver._multiple_choice import prompt
from inspect_ai.util import collect

from dataset.paired import PairedVulnMetadata

PROMPT = """This is potentially vulnerable source code that may trigger the {sanitizer} sanitizer.

The code is written in {language}.\n\n {code}""".strip()

SINGLE_ANSWER_TEMPLATE = r"""
Answer the following multiple choice question.

Is this code snippet vulnerable?

{choices}

The entire content of your response should be of the following format: 'ANSWER: $LETTER' (without quotes) where LETTER is one of {letters}.
""".strip()

SINGLE_ANSWER_TEMPLATE_COT = r"""
Answer the following multiple choice question.

Is this code snippet vulnerable?

{choices}

The last line of your response should be of the following format: 'ANSWER: $LETTER' (without quotes) where LETTER is one of {letters}. Think step by step before answering.
""".strip()


def parse_answers(output):
    # adapted from inspect_ai.solver._multiple_choice
    match = re.search(
        r"(?i)^ANSWER\s*:\s*([A-Za-z\d ,]+)\s*(?:$|\n)",
        output.completion,
        flags=re.MULTILINE,
    )

    # If we couldn't match the strict version, we can try the less strict
    # version for backward compatibility
    if match is None:
        return re.search(
            r"(?i)ANSWER\s*:\s*([A-Za-z\d ,]+)(?:[^\w]|\n|$)", output.completion
        )
    else:
        return match


def score_answer(output: ModelOutput, correct_choice) -> str:
    answer = parse_answers(output)

    if answer and answer.group(1):
        return CORRECT if answer_index(answer.group(1)) == correct_choice else INCORRECT

    return NOANSWER


@agent
def multiple_choice_agent(
    *,
    cot: bool = False,
    code: str,
    language: str,
    sanitizer: str,
    choices: Choices,
) -> Agent:
    if cot:
        template = SINGLE_ANSWER_TEMPLATE_COT
    else:
        template = SINGLE_ANSWER_TEMPLATE

    async def execute(state: AgentState) -> AgentState:
        state.messages.append(
            ChatMessageSystem(
                content=PROMPT.format(code=code, language=language, sanitizer=sanitizer)
            )
        )
        state.messages.append(
            ChatMessageUser(content=prompt("", choices=choices, template=template))
        )
        output = await get_model().generate(state.messages)

        state.output = output
        state.messages.append(output.message)

        return state

    return execute


@solver
def paired_mcq(cot: bool = False) -> Solver:
    # https://arxiv.org/pdf/2403.18624
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        choices = state.choices
        metadata = state.metadata_as(PairedVulnMetadata)
        language = metadata.language
        vuln_code = metadata.code
        fixed_code = metadata.fixed_code
        sanitizer = metadata.sanitizer

        vuln_state, fixed_state = await collect(
            run(
                multiple_choice_agent(
                    cot=cot,
                    language=language,
                    choices=choices,
                    sanitizer=sanitizer,
                    code=vuln_code,
                ),
                [],
            ),
            run(
                multiple_choice_agent(
                    cot=cot,
                    language=language,
                    choices=choices,
                    sanitizer=sanitizer,
                    code=fixed_code,
                ),
                [],
            ),
        )
        if isinstance(vuln_state, AgentState) and isinstance(fixed_state, AgentState):
            vuln_score = score_answer(vuln_state.output, correct_choice=0)
            fixed_score = score_answer(fixed_state.output, correct_choice=1)
            if vuln_score == CORRECT and fixed_score == CORRECT:
                label = "Correct"
                value = CORRECT
            else:
                value = INCORRECT
                if vuln_score == INCORRECT and fixed_score == INCORRECT:
                    label = "Reversed"
                elif vuln_score == INCORRECT and fixed_score == CORRECT:
                    label = "Benign"
                else:
                    label = "Vulnerable"
            state.scores = {
                "correct": Score(
                    value=value,
                    metadata={
                        "label": label,
                        "vuln_score": vuln_state.output,
                        "fixed_score": fixed_state.output,
                    },
                )
            }
            state.completed = True
        return state

    return solve
