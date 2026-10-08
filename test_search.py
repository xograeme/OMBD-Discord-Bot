import asyncio
import os

import aiohttp
from dotenv import load_dotenv

load_dotenv()
OMDB_API_KEY = os.getenv("OMDB_API_KEY")

async def fetch_omdb_search(query: str, type_filter: str = "movie", max_pages: int = 5) -> list:
    results = []
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for page in range(1, max_pages + 1):
            params = {
                "s": query,
                "apikey": OMDB_API_KEY,
                "type": type_filter,
                "page": str(page)
            }
            async with session.get("https://www.omdbapi.com/", params=params) as response:
                response.raise_for_status()
                data = await response.json()
                print(f"Page {page} response: {data.get('Response')}")
                if data.get("Response") == "True":
                    search_results = data.get("Search", [])
                    results.extend(search_results)
                    if len(search_results) < 10:
                        break
                else:
                    print(f"OMDB Error: {data.get('Error')}")
                    break
    
    unique_results = {movie.get('imdbID'): movie for movie in results if movie.get('imdbID')}.values()
    return list(unique_results)

async def main():
    movies = await fetch_omdb_search("Star Wars")
    print(f"Found {len(movies)} movies.")
    
    movies_sorted = sorted(movies, key=lambda m: m.get("Year", "0")[:4])
    for m in movies_sorted:
        print(m.get("Title"), m.get("Year"))

if __name__ == "__main__":
    asyncio.run(main())
