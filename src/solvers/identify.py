PROMPT = """This is vulnerable source code written in {language}.\n\n {code}""".strip()

SINGLE_ANSWER_TEMPLATE = r"""
{question}

Answer the following multiple choice question.

Which sanitizer does the bug in this code trigger?

{choices}

The entire content of your response should be of the following format: 'ANSWER: $LETTER' (without quotes) where LETTER is one of {letters}.
""".strip()

SINGLE_ANSWER_TEMPLATE_COT = r"""
{question}

Answer the following multiple choice question.

Which sanitizer does the bug in this code trigger?

{choices}

The last line of your response should be of the following format: 'ANSWER: $LETTER' (without quotes) where LETTER is one of {letters}. Think step by step before answering.
""".strip()
