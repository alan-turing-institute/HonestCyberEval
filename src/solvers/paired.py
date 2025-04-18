PROMPT = """This is potentially vulnerable source code that may trigger the {sanitizer} sanitizer.

The code is written in {language}.\n\n {code}""".strip()

SINGLE_ANSWER_TEMPLATE = r"""
{question}

Answer the following multiple choice question.

Is this code snippet vulnerable?

{choices}

The entire content of your response should be of the following format: 'ANSWER: $LETTER' (without quotes) where LETTER is one of {letters}.
""".strip()

SINGLE_ANSWER_TEMPLATE_COT = r"""
{question}

Answer the following multiple choice question.

Is this code snippet vulnerable?

{choices}

The last line of your response should be of the following format: 'ANSWER: $LETTER' (without quotes) where LETTER is one of {letters}. Think step by step before answering.
""".strip()
