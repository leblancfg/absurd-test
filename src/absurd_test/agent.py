import random
import time
from functools import lru_cache

from pydantic_ai import Agent

from absurd_test.config import get_settings
from absurd_test.oblique_strategies import OBLIQUE_STRATEGIES


@lru_cache
def get_agent() -> Agent:
    """Lazily create the agent (defers API key check until needed)."""
    return Agent(
        "openai:gpt-5.1",
        instructions="You are a helpful assistant. Be concise and direct.",
    )


def run_agent_kiosk(prompt: str) -> str:
    """Return an Oblique Strategy with a jittery 3 second delay."""
    # Jittery delay: 3 seconds +/- 0.5 seconds
    delay = 3.0 + random.uniform(-0.5, 0.5)
    time.sleep(delay)

    # Return a random Oblique Strategy
    strategy = random.choice(OBLIQUE_STRATEGIES)
    return strategy


def run_agent(prompt: str) -> str:
    """Run the agent synchronously and return the result."""
    settings = get_settings()

    if settings.kiosk:
        return run_agent_kiosk(prompt)

    agent = get_agent()
    result = agent.run_sync(prompt)
    return result.output
