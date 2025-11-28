from functools import lru_cache

from pydantic_ai import Agent


@lru_cache
def get_agent() -> Agent:
    """Lazily create the agent (defers API key check until needed)."""
    return Agent(
        "openai:gpt-5.1",
        instructions="You are a helpful assistant. Be concise and direct.",
    )


def run_agent(prompt: str) -> str:
    """Run the agent synchronously and return the result."""
    agent = get_agent()
    result = agent.run_sync(prompt)
    return result.output
