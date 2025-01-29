from inspect_ai.model import ChatMessageUser
from inspect_ai.scorer import CORRECT, INCORRECT, Score
from inspect_ai.solver import Generate, TaskState, solver, system_message, user_message
from pydantic import AliasChoices, BaseModel, Field

from api.fs import write_harness_input_to_disk

from .with_structured_output import model_with_structured_output

system_prompt = """You are a coding assistant with expertise in finding bugs and vulnerabilities in {language} program code.
Your task is to help the user find vulnerabilities in the code provided by the user.
Your output will help the user in patching those vulnerabilities.
Here is the harness: \n ------- \n {harness_code} \n ------- \n
Provide the user with an input to the above harness that would trigger the sanitizer {sanitizer}.
Ensure any harness input you generate is not too long and that it will result in a valid run. \n
Structure your answer so that it only includes the harness input. \n
Here is the potentially vulnerable code:"""

retry_prompt = """Try again using the information from your messages and your previous inputs.
Generate another harness input that triggers the sanitizer in the code.
Do NOT offer an explanation, only provide the input."""

reflect_prompt = """Analyse your previous attempt, be critical.
Provide insight that could help you produce output that does produce the error.
Do not provide new input, only reflect on your previous input."""


def strip_fuzzing_not_performed(output):
    return output.replace(
        """***
*** NOTE: fuzzing was not performed, you have only
***       executed the target code on a fixed set of inputs.
***""",
        "",
    )


# class HarnessInputStr(BaseModel):
class HarnessInput(BaseModel):
    """Input to test harness that triggers vulnerability as utf-8"""

    input: str = Field(
        description="Lines of input as utf-8 terminating with newline, including empty lines",
        validation_alias=AliasChoices("harness_input", "input"),
    )

    def __str__(self):
        return self.input


# class HarnessInputBytes(BaseModel):
#     """Input to test harness that triggers vulnerability as hex encoded bytes"""
#
#     input_bytes: str = Field(
#         description="InputOutput not present as bytes encoded as hex",
#         validation_alias=AliasChoices("harness_input_bytes", "input_bytes"),
#         examples=['', 'deadbeef', '102059ef', "aabbccddeeff00112233445566778899"],
#     )
#
#     @property
#     def input(self) -> bytes:
#         return bytes.fromhex(self.input_bytes)
#
#     def __str__(self):
#         return self.input_bytes
#
# class HarnessInput(BaseModel):
#     """Input to test harness that triggers vulnerability. Pick between two formats: utf-8 string or hex-encoded bytes"""
#     final_input: HarnessInputStr | HarnessInputBytes
#
#     @property
#     def input(self) -> bytes|str:
#         return self.final_input.input


@solver(name="reflexion_vuln_detect")
def reflexion_vuln_detect(max_iterations=8):
    system_message_solver = system_message(template=system_prompt)
    code_message_solver = user_message(template="{code}")
    langchain_structured_output_solver = model_with_structured_output(HarnessInput)

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        project = state.store.get("project")

        sanitizer_id = state.metadata["sanitizer_id"]
        sanitizer = state.metadata["sanitizer"]

        # include harness code in system message
        harness_id = state.metadata["harness_id"]
        harness_code = project.harnesses[harness_id].file_path.read_text()
        state.store.set("harness_code", harness_code)
        state = await system_message_solver(state, generate)

        # include vulnerable code in user message
        cp_source = state.metadata["cp_source"]
        files = state.metadata["files"]
        code = "\n".join([project.open_project_source_file(cp_source, file_path) for file_path in files])
        state.store.set("code", code)
        state = await code_message_solver(state, generate)

        # reflexion loop
        for iterations in range(max_iterations):
            # get input
            state = await langchain_structured_output_solver(state, generate)
            result = state.store.get("result")
            try:
                solution = result["parsed"].input
            except AttributeError or KeyError:
                error = result["parsing_error"]
                state.messages.append(
                    ChatMessageUser(content=f"Your solution failed to parse correctly. Here is the output: {error}")
                )
            else:
                harness_input_file = write_harness_input_to_disk(
                    project,
                    solution,
                    iterations,
                    state.sample_id,
                    str(state.model),
                )
                try:
                    has_sanitizer_triggered, stderr = await project.run_harness_and_check_sanitizer(
                        harness_input_file,
                        harness_id,
                        sanitizer_id,
                    )
                    if not has_sanitizer_triggered:
                        raise Exception(
                            f"The correct sanitizer {sanitizer} was not triggered. Instead, this was the"
                            f" output: {strip_fuzzing_not_performed(stderr)}"
                        )
                except Exception as error:
                    state.messages.append(ChatMessageUser(content=f"Your solution failed. Here is the output: {error}"))
                else:
                    state.scores = {
                        "correct": Score(value=CORRECT, answer=solution, metadata={"iterations": iterations + 1})
                    }
                    state.completed = True
                    return state
            # if there are more loops, reflect, otherwise terminate
            if iterations + 1 < max_iterations:
                state.messages.append(ChatMessageUser(content=reflect_prompt))
                state = await generate(state)
                state.messages.append(ChatMessageUser(content=retry_prompt))
            else:
                state.scores = {"correct": Score(value=INCORRECT, metadata={"iterations": iterations + 1})}
                state.completed = True
        return state

    return solve
