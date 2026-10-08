import aiohttp
import os
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

TMDB_ACCESS_TOKEN = os.getenv("TMDB_ACCESS_TOKEN")

TMDB_GENRES = {
    "action": 28,
    "animation": 16,
    "comedy": 35,
    "drama": 18,
    "fantasy": 14,
    "horror": 27,
    "mystery": 9648,
    "romance": 10749,
    "sci-fi": 878,
    "thriller": 53
}

async def fetch_tmdb_person_id(name: str) -> int | None:
    """Search TMDB for a person and return their ID."""
    if not TMDB_ACCESS_TOKEN:
        return None
        
    url = f"https://api.themoviedb.org/3/search/person?query={urllib.parse.quote(name)}&include_adult=false&language=en-US&page=1"
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_ACCESS_TOKEN}"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])
                    if results:
                        return results[0]["id"]
    except Exception as e:
        print(f"Error fetching TMDB person ID: {e}")
        
    return None

async def fetch_tmdb_tv_id(imdb_id: str) -> int | None:
    """Find TMDB TV ID from an IMDb ID."""
    if not TMDB_ACCESS_TOKEN:
        return None
        
    url = f"https://api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id"
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_ACCESS_TOKEN}"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    tv_results = data.get("tv_results", [])
                    if tv_results:
                        return tv_results[0]["id"]
    except Exception as e:
        print(f"Error fetching TMDB TV ID: {e}")
        
    return None

async def discover_movies(genre: str = None, person_name: str = None) -> list:
    """Discover movies using TMDB by genre and/or person (cast)."""
    if not TMDB_ACCESS_TOKEN:
        return []
        
    params = [
        "include_adult=false",
        "include_video=false",
        "language=en-US",
        "page=1",
        "sort_by=popularity.desc"
    ]
    
    if genre and genre.lower() in TMDB_GENRES:
        params.append(f"with_genres={TMDB_GENRES[genre.lower()]}")
        
    if person_name:
        person_id = await fetch_tmdb_person_id(person_name)
        if person_id:
            params.append(f"with_cast={person_id}")
            
    url = f"https://api.themoviedb.org/3/discover/movie?{'&'.join(params)}"
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_ACCESS_TOKEN}"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("results", [])
    except Exception as e:
        print(f"Error fetching TMDB discover: {e}")
        
    return []
