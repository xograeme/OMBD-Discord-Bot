import asyncio
import os

import aiohttp
from dotenv import load_dotenv

load_dotenv()
OMDB_API_KEY = os.getenv("OMDB_API_KEY")

from bot import fetch_omdb_search

async def main():
    async with aiohttp.ClientSession() as session:
        movies = await fetch_omdb_search(session, "Star Wars")
        print(f"Found {len(movies)} movies.")
        
        movies_sorted = sorted(movies, key=lambda m: m.get("Year", "0")[:4])
        for m in movies_sorted:
            print(m.get("Title"), m.get("Year"))

if __name__ == "__main__":
    asyncio.run(main())
