"""Quick manual test for the Jev natural-language layer used by bot.py."""
import asyncio
import logging

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

from jev_client import JevClient, extract_title  # noqa: E402  (needs .env loaded first)

SAMPLES = [
    "show me the trailer for Dune",
    "can you show me the Dune trailer?",
    "recommend me a scary movie",
    "got any good anime films?",
    "tell me about Inception",
    "what's the plot of The Matrix (1999)",
    "is Get Out any good?",
    "add Interstellar to the watchlist",
    "what's on our watchlist?",
    "show my watchlist",
    "hi there",
]


async def main():
    client = JevClient()
    for text in SAMPLES:
        analysis = await client.analyze(text)
        title, year = extract_title(text)
        print(
            f"{text!r:45} -> intent={analysis['intent']:<16} genre={analysis['genre']:<10} "
            f"watchlist={analysis['watchlist_action']:<14} title={title!r} year={year}"
        )


if __name__ == "__main__":
    asyncio.run(main())