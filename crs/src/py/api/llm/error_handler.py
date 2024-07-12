import asyncio
from typing import List, NoReturn

from openai import APIStatusError, RateLimitError

from logger import logger


class ErrorHandler(Exception):

    RETRIES: int = 4
    DELAYS: List[float] = [10, 20, 30, 60]

    def __init__(self):
        self.attempts = -1

    def raise_exception(self) -> NoReturn:
        raise Exception(f"Too many retries ({self.attempts}) to get a response from the LLM provider.")

    def ok_to_retry(self):
        self.attempts += 1
        return self.attempts < self.RETRIES

    async def exception_caught(self, e):
        logger.debug(f"Error details: {e}")
        if isinstance(e, APIStatusError) and e.status_code == 500:
            logger.info(f"Error 500. Retrying in {self.DELAYS[self.attempts]} secs.")
            await asyncio.sleep(self.DELAYS[self.attempts])
        elif isinstance(e, RateLimitError):
            logger.info(f"Error 429. Retrying in {self.DELAYS[self.attempts]} secs.")
            await asyncio.sleep(self.DELAYS[self.attempts])
        elif isinstance(e, APIStatusError) and e.status_code == 400:
            logger.info(f"Error 400. This is the anthropic weirdness; we throw.")
            raise  # logger picks it up on the other side.
        else:
            raise  # logger picks it up on the other side.
