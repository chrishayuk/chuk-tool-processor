"""
Minimal “tools-with-OpenAI” example.
All tools live in sample_tools/*.py and are imported just for their
side-effect of registration.
"""
from __future__ import annotations

import asyncio
import os
from pprint import pprint  # <-- use the function directly
from dotenv import load_dotenv
from openai import AsyncOpenAI

# --------------------------------------------------------------------------- #
# chuk-tool-processor bits
# --------------------------------------------------------------------------- #
from chuk_tool_processor.core.processor import ToolProcessor
from chuk_tool_processor.registry.tool_export import openai_functions

# Import tools so they self-register (unused-import pragma just keeps linters quiet)
from sample_tools import WeatherTool, SearchTool, CalculatorTool  # noqa: F401

# --------------------------------------------------------------------------- #
# environment
# --------------------------------------------------------------------------- #
load_dotenv()


async def ensure_openai_ok() -> AsyncOpenAI:
    """Return an AsyncOpenAI client, raising if the key is missing/invalid."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Set OPENAI_API_KEY in environment or .env")

    client = AsyncOpenAI(api_key=key)

    # Quick ping - will raise if the credentials are invalid
    await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "ping"}],
    )
    return client


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
async def main() -> None:
    client = await ensure_openai_ok()

    # Processor with built-in OpenAI-response parser
    processor = ToolProcessor(enable_caching=True, enable_retries=True)

    prompt = (
        "I need to know if I should wear a jacket today in New York.\n"
        "Also, how much is 235.5 × 18.75?\n"
        "Finally, find a couple of pages on climate-change adaptation."
    )

    # Ask the LLM; let it decide which tools to invoke
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        tools=openai_functions(),   # ← one-liner conversion!
        tool_choice="auto",
        temperature=0.7,
    )

    msg = response.choices[0].message

    # Run whatever tool calls the model produced
    tool_results = await processor.process_text(msg.model_dump())

    # ------------------------------------------------------------------ #
    # Pretty-print results
    # ------------------------------------------------------------------ #
    if msg.content:
        print("\nLLM reply (no tool calls):")
        print(msg.content)

    print(f"\nExecuted {len(tool_results)} tool calls")
    for res in tool_results:
        print(f"\n⮑  {res.tool}")
        # res.result is a Pydantic model → convert to dict before printing
        pprint(res.result.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
