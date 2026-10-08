import asyncio
import os
import random
import re
import sqlite3
import urllib.parse
import urllib.request

import aiohttp
import discord
from discord import app_commands
from dotenv import load_dotenv

from jev_client import JevClient, extract_title, extract_person
import tmdb_client


# Read your private keys from .env
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")

if not DISCORD_TOKEN or not OMDB_API_KEY:
    raise RuntimeError("Add DISCORD_TOKEN and OMDB_API_KEY to your .env file.")

# Database Initialization
def init_db():
    conn = sqlite3.connect("watchlists.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            movie_title TEXT NOT NULL,
            added_by INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            movie_title TEXT NOT NULL,
            marked_by INTEGER NOT NULL,
            watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS personal_watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            movie_title TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

def run_db_query(query, params=(), fetch=False, fetchall=False):
    conn = sqlite3.connect("watchlists.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    
    result = None
    if fetch:
        result = cursor.fetchone()
    elif fetchall:
        result = cursor.fetchall()
        
    conn.commit()
    conn.close()
    return result

async def async_db_query(query, params=(), fetch=False, fetchall=False):
    return await asyncio.to_thread(run_db_query, query, params, fetch, fetchall)

def run_db_execute_many(query, params_list):
    conn = sqlite3.connect("watchlists.db")
    cursor = conn.cursor()
    cursor.executemany(query, params_list)
    conn.commit()
    conn.close()

async def async_db_execute_many(query, params_list):
    await asyncio.to_thread(run_db_execute_many, query, params_list)


# Curated dataset of highly acclaimed movies categorized by genre
RECOMMENDED_MOVIES = {
    "action": [
        "The Dark Knight", "Mad Max: Fury Road", "Die Hard", "John Wick", "Gladiator",
        "Raiders of the Lost Ark", "Terminator 2: Judgment Day", "Aliens",
        "Spider-Man: Into the Spider-Verse", "Mission: Impossible - Fallout",
        "Top Gun: Maverick", "The Matrix", "Casino Royale", "Speed",
        "Kill Bill: Vol. 1", "Avengers: Endgame", "The Bourne Ultimatum", "Lethal Weapon",
        "Logan", "Heat"
    ],
    "sci-fi": [
        "Inception", "Interstellar", "Blade Runner 2049", "Dune", "Arrival",
        "Alien", "2001: A Space Odyssey", "Back to the Future", "Jurassic Park",
        "Eternal Sunshine of the Spotless Mind", "The Thing",
        "Star Wars: Episode V - The Empire Strikes Back", "Ex Machina",
        "District 9", "The Prestige", "Children of Men", "The Matrix", "Avatar",
        "Snowpiercer", "Minority Report"
    ],
    "comedy": [
        "Superbad", "The Grand Budapest Hotel", "Monty Python and the Holy Grail",
        "Groundhog Day", "Shaun of the Dead", "The Big Lebowski", "Hot Fuzz",
        "Airplane!", "Office Space", "Knives Out", "Tropic Thunder",
        "What We Do in the Shadows", "Ferris Bueller's Day Off", "Dumb and Dumber",
        "Mean Girls", "Step Brothers", "Anchorman", "Ghostbusters"
    ],
    "drama": [
        "The Shawshank Redemption", "The Godfather", "Fight Club", "Forrest Gump",
        "Whiplash", "Oppenheimer", "Parasite", "12 Angry Men", "Schindler's List",
        "Good Will Hunting", "The Social Network", "There Will Be Blood",
        "Dead Poets Society", "The Green Mile", "A Beautiful Mind", "The Pursuit of Happyness",
        "Manchester by the Sea", "Requiem for a Dream"
    ],
    "horror": [
        "The Shining", "Get Out", "The Thing", "A Nightmare on Elm Street", "Psycho",
        "Hereditary", "Halloween", "The Exorcist", "The Silence of the Lambs",
        "A Quiet Place", "Alien", "Scream", "The Conjuring", "It Follows", "Midsommar",
        "The Babadook", "Rosemary's Baby", "Sinister", "The Descent"
    ],
    "animation": [
        "Spirited Away", "Spider-Man: Into the Spider-Verse", "WALL-E", "Toy Story",
        "Princess Mononoke", "Spider-Man: Across the Spider-Verse", "The Lion King",
        "Up", "Ratatouille", "Inside Out", "Your Name.", "Howl's Moving Castle",
        "The Iron Giant", "Fantastic Mr. Fox", "Coco", "Finding Nemo",
        "Shrek", "The Incredibles"
    ],
    "thriller": [
        "Se7en", "The Silence of the Lambs", "Parasite", "Shutter Island",
        "Gone Girl", "Prisoners", "No Country for Old Men", "The Prestige",
        "Memento", "Zodiac", "Nightcrawler", "Sicario", "Black Swan",
        "The Usual Suspects", "A Quiet Place", "Fargo", "Oldboy"
    ],
    "romance": [
        "La La Land", "Eternal Sunshine of the Spotless Mind", "Before Sunrise",
        "Pride & Prejudice", "About Time", "(500) Days of Summer", "Titanic",
        "Casablanca", "Her", "The Princess Bride", "Portrait of a Lady on Fire",
        "The Notebook", "Crazy Rich Asians", "Silver Linings Playbook", "A Star is Born"
    ],
    "mystery": [
        "Knives Out", "Se7en", "Pulp Fiction", "The Usual Suspects", "Glass Onion",
        "Zodiac", "L.A. Confidential", "Chinatown", "Rear Window",
        "Memories of Murder", "Sherlock Holmes", "The Girl with the Dragon Tattoo",
        "Prisoners", "Shutter Island", "The Sixth Sense", "Vertigo"
    ],
    "fantasy": [
        "The Lord of the Rings: The Fellowship of the Ring", "Pan's Labyrinth",
        "Spirited Away", "Harry Potter and the Prisoner of Azkaban", "Stardust",
        "The Princess Bride", "How to Train Your Dragon", "Big Fish",
        "Alice in Wonderland", "The Chronicles of Narnia", "The Wizard of Oz",
        "Pirates of the Caribbean: The Curse of the Black Pearl"
    ],
    "documentary": [
        "Free Solo", "Won't You Be My Neighbor?", "Jiro Dreams of Sushi",
        "13th", "Apollo 11", "My Octopus Teacher", "March of the Penguins",
        "Man on Wire", "Senna", "Blackfish"
    ],
    "family": [
        "Paddington 2", "The Lion King", "Toy Story", "E.T. the Extra-Terrestrial",
        "Mary Poppins", "Willy Wonka & the Chocolate Factory", "Home Alone",
        "The Goonies", "The Princess Bride", "Matilda"
    ],
    "adventure": [
        "Indiana Jones and the Raiders of the Lost Ark", "Jurassic Park",
        "The Lord of the Rings: The Two Towers", "Pirates of the Caribbean",
        "Jumanji: Welcome to the Jungle", "The Mummy", "King Kong",
        "National Treasure", "The Goonies", "Mad Max: Fury Road"
    ],
    "crime": [
        "The Godfather", "Goodfellas", "Pulp Fiction", "The Departed",
        "City of God", "Heat", "Casino", "The Usual Suspects",
        "Snatch", "Scarface"
    ],
    "anime": [
        "Akira", "Ghost in the Shell", "Your Name.", "Spirited Away",
        "Princess Mononoke", "A Silent Voice", "Perfect Blue",
        "Neon Genesis Evangelion: The End of Evangelion", "Grave of the Fireflies",
        "Howl's Moving Castle", "Weathering with You", "Demon Slayer: Mugen Train"
    ]
}


async def fetch_youtube_trailer(query: str) -> str:
    """Fetches the first YouTube search result URL for a given query."""
    def _search():
        search_query = urllib.parse.quote(f"{query} official trailer")
        url = f"https://www.youtube.com/results?search_query={search_query}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            html = urllib.request.urlopen(req, timeout=5)
            video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
            if video_ids:
                return f"https://www.youtube.com/watch?v={video_ids[0]}"
        except Exception as e:
            print(f"Error fetching trailer: {e}")
        return None
    return await asyncio.to_thread(_search)


async def fetch_omdb_data(title: str, year: int = None) -> dict:
    """Fetch movie details from OMDb API asynchronously."""
    params = {
        "t": title,
        "apikey": OMDB_API_KEY,
        "plot": "short"
    }
    if year is not None:
        params["y"] = str(year)

    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get("https://www.omdbapi.com/", params=params) as response:
            response.raise_for_status()
            return await response.json()


async def fetch_omdb_search(query: str, type_filter: str = "movie", max_pages: int = 5) -> list:
    """Fetch a list of search results from OMDb API asynchronously (handles pagination)."""
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
                if data.get("Response") == "True":
                    search_results = data.get("Search", [])
                    results.extend(search_results)
                    if len(search_results) < 10:
                        break
                else:
                    break
    
    unique_results = {movie.get('imdbID'): movie for movie in results if movie.get('imdbID')}.values()
    return list(unique_results)


def build_movie_embed(
    movie_info: dict,
    custom_header: str = None,
    footer_text: str = None
) -> discord.Embed:
    """Format movie information into a Discord embed."""
    def info(key):
        value = movie_info.get(key)
        if not value or value == "N/A":
            return "Not available"
        return str(value)

    def shorten(text, limit):
        return text if len(text) <= limit else text[:limit - 1] + "…"

    title_text = f"{info('Title')} ({info('Year')})"
    if custom_header:
        title_text = f"{custom_header} {title_text}"

    embed = discord.Embed(
        title=shorten(title_text, 256),
        description=shorten(info("Plot"), 1200),
        colour=discord.Colour.gold()
    )

    # Make the title clickable if IMDb ID is available
    imdb_id = movie_info.get("imdbID", "")
    if imdb_id.startswith("tt"):
        embed.url = f"https://www.imdb.com/title/{imdb_id}/"

    # Show the poster when available
    poster = movie_info.get("Poster", "")
    if poster.startswith(("https://", "http://")):
        embed.set_image(url=poster)

    # Main IMDb ratings
    rating = info("imdbRating")
    if rating != "Not available":
        rating += " / 10"

    embed.add_field(name="⭐ IMDb", value=rating, inline=True)
    embed.add_field(
        name="🎬 Content rating",
        value=info("Rated"),
        inline=True
    )

    # Detailed fields
    fields = [
        ("⏱️ Runtime", "Runtime", True),
        ("📅 Released", "Released", True),
        ("📺 Type", "Type", True),
        ("🎭 Genre", "Genre", False),
        ("🎥 Director", "Director", True),
        ("✍️ Writer", "Writer", True),
        ("🌍 Country", "Country", True),
        ("👥 Cast", "Actors", False),
        ("🗣️ Language", "Language", True),
        ("💰 Box office", "BoxOffice", True),
        ("🏆 Awards", "Awards", False),
    ]

    for label, key, inline in fields:
        embed.add_field(
            name=label,
            value=shorten(info(key), 200),
            inline=inline
        )

    if movie_info.get("totalSeasons") not in (None, "N/A"):
        embed.add_field(
            name="Seasons",
            value=info("totalSeasons"),
            inline=True
        )

    default_footer = "Movie & TV Search • Data from OMDb • Click the title for IMDb"
    embed.set_footer(text=footer_text or default_footer)

    return embed


class RecommendView(discord.ui.View):
    """View containing the interactive 'Recommend Another' re-roll button."""
    def __init__(self, genre: str = None, person_name: str = None, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.genre = genre
        self.person_name = person_name

    @discord.ui.button(
        label="Recommend Another",
        style=discord.ButtonStyle.primary,
        emoji="🎲"
    )
    async def recommend_another(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.defer()

        chosen_title = await pick_recommendation(self.genre, self.person_name)

        try:
            movie_info = await fetch_omdb_data(chosen_title)
            if movie_info.get("Response") == "True":
                header_parts = []
                if self.genre: header_parts.append(self.genre.title())
                if self.person_name: header_parts.append(f"w/ {self.person_name}")
                header_str = f" [{', '.join(header_parts)}]" if header_parts else " [All Genres]"
                embed = build_movie_embed(
                    movie_info,
                    custom_header=f"🎲 Recommended{header_str}:",
                    footer_text="Movie Recommendation • Data from TMDB/OMDb • Click title for IMDb"
                )
                if getattr(self, "watch_enabled", False):
                    await add_watch_button(self, movie_info)
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.followup.send(
                    f"Couldn't load details for '{chosen_title}'. Please try clicking again!",
                    ephemeral=True
                )
        except Exception:
            await interaction.followup.send(
                "An error occurred while fetching the recommendation.",
                ephemeral=True
            )


class MovieActionView(discord.ui.View):
    """View containing buttons to add a movie to watchlists."""
    def __init__(self, movie_title: str, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.movie_title = movie_title

    @discord.ui.button(
        label="Server Watchlist",
        style=discord.ButtonStyle.success,
        emoji="🍿"
    )
    async def add_server_watchlist(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            await interaction.followup.send("You can only add to the server watchlist within a server.")
            return
            
        await async_db_query(
            "INSERT INTO server_watchlist (guild_id, movie_title, added_by) VALUES (?, ?, ?)",
            (interaction.guild_id, self.movie_title, interaction.user.id)
        )
        await interaction.followup.send(f"✅ Added **{self.movie_title}** to the server watchlist!")

    @discord.ui.button(
        label="Personal Watchlist",
        style=discord.ButtonStyle.secondary,
        emoji="👤"
    )
    async def add_personal_watchlist(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await async_db_query(
            "INSERT INTO personal_watchlist (user_id, movie_title) VALUES (?, ?)",
            (interaction.user.id, self.movie_title)
        )
        await interaction.followup.send(f"✅ Added **{self.movie_title}** to your personal watchlist!")


# ---------- Shared helpers (used by slash commands and natural-language chat) ----------

async def add_watch_button(view: discord.ui.View, movie_info: dict, season: int = None, episode: int = None):
    """Add a 'Watch Now' link button using the OMDb imdbID. Skipped if the ID is missing."""
    old_button = getattr(view, "watch_button", None)
    if old_button is not None:
        view.remove_item(old_button)
        view.watch_button = None
    view.watch_enabled = True

    imdb_id = movie_info.get("imdbID")
    if not imdb_id or imdb_id == "N/A":
        return

    is_series = movie_info.get("Type") == "series"
    if is_series:
        s = season if season is not None else 1
        e = episode if episode is not None else 1
        tmdb_id = await tmdb_client.fetch_tmdb_tv_id(imdb_id)
        show_id = tmdb_id if tmdb_id else imdb_id
        url = f"https://velarium.cc/en/watch/tv/{show_id}-{s}-{e}?autoPlay=true&autoNext=true"
    else:
        url = f"https://velarium.cc/embed/movie/{imdb_id}"

    view.watch_button = discord.ui.Button(
        style=discord.ButtonStyle.link,
        label="Watch Now",
        emoji="🍿",
        url=url
    )
    view.add_item(view.watch_button)


async def pick_recommendation(genre: str = None, person_name: str = None) -> str:
    """Pick a random title, optionally from a specific genre and/or actor/director."""
    if tmdb_client.TMDB_ACCESS_TOKEN and (genre or person_name):
        movies = await tmdb_client.discover_movies(genre, person_name)
        if movies:
            return random.choice(movies)["title"]

    if genre and genre.lower() in RECOMMENDED_MOVIES:
        pool = RECOMMENDED_MOVIES[genre.lower()]
    else:
        pool = [title for sublist in RECOMMENDED_MOVIES.values() for title in sublist]
    return random.choice(pool)


async def lookup_movie(title: str, year: int = None) -> dict:
    """OMDb lookup that retries without a leading 'the' (common in chat phrasing)."""
    movie_info = await fetch_omdb_data(title, year)
    if movie_info.get("Response") != "True" and title.lower().startswith("the "):
        retry = await fetch_omdb_data(title[4:], year)
        if retry.get("Response") == "True":
            return retry
    return movie_info


async def resolve_canonical_title(title: str, year: int = None) -> str:
    """Turn user input into 'Title (Year)' using OMDb, falling back to the raw input."""
    try:
        movie_info = await lookup_movie(title, year)
        if movie_info.get("Response") == "True":
            return f"{movie_info.get('Title')} ({movie_info.get('Year')})"
    except Exception:
        pass
    return title.strip()


def _list_embed(title: str, lines: list, colour: discord.Colour) -> discord.Embed:
    description = "\n".join(lines)
    if len(description) > 4000:
        description = description[:4000] + "\n...and more!"
    return discord.Embed(title=title, description=description, color=colour)


async def server_watchlist_embed(guild_id: int):
    """Embed of the server watchlist, or None if it's empty."""
    rows = await async_db_query(
        "SELECT movie_title, added_by FROM server_watchlist WHERE guild_id = ? ORDER BY added_at ASC",
        (guild_id,), fetchall=True
    )
    if not rows:
        return None
    lines = [f"**{i}.** {m_title} *(added by <@{added_by}>)*" for i, (m_title, added_by) in enumerate(rows, 1)]
    return _list_embed("🍿 Server Watchlist", lines, discord.Color.blue())


async def personal_watchlist_embed(user: discord.abc.User):
    """Embed of a user's personal watchlist, or None if it's empty."""
    rows = await async_db_query(
        "SELECT movie_title FROM personal_watchlist WHERE user_id = ? ORDER BY added_at ASC",
        (user.id,), fetchall=True
    )
    if not rows:
        return None
    lines = [f"**{i}.** {m_title}" for i, (m_title,) in enumerate(rows, 1)]
    return _list_embed(f"🍿 {user.display_name}'s Watchlist", lines, discord.Color.purple())


# ---------- Natural-language chat powered by FreeJev ----------

jev = JevClient()

CHAT_HELP = (
    "🎬 **Just ask me in plain English!** For example:\n"
    "• *Tell me about Inception*\n"
    "• *Recommend me a scary movie*\n"
    "• *Show me the trailer for Dune*\n"
    "• *Add Interstellar to the watchlist*\n"
    "• *What's on our watchlist?* / *Show my watchlist*\n\n"
    "Mention me, DM me, or use `/ask`. Slash commands like `/movie` and `/recommend` still work too."
)


async def handle_natural_request(text: str, user: discord.abc.User, guild_id: int = None) -> dict:
    """
    Classify a chat message with Jev and run the matching bot feature.
    Returns send() kwargs plus a 'private' flag for results only the user should see.
    """
    analysis = await jev.analyze(text)
    intent = analysis["intent"]
    print(f"[Jev] {user} -> {analysis} :: {text!r}")

    if not analysis["ok"]:
        return {"content": "⚠️ I'm having trouble understanding messages right now.\n\n" + CHAT_HELP}

    try:
        if intent == "recommend":
            genre = None if analysis["genre"] == "any" else analysis["genre"]
            person_name = extract_person(text)
            chosen_title = await pick_recommendation(genre, person_name)
            movie_info = await fetch_omdb_data(chosen_title)
            if movie_info.get("Response") != "True":
                return {"content": f"Could not load recommendation for '{chosen_title}'. Please try again."}
            
            header_parts = []
            if genre: header_parts.append(genre.title())
            if person_name: header_parts.append(f"w/ {person_name}")
            header_str = f" [{', '.join(header_parts)}]" if header_parts else " [All Genres]"
            embed = build_movie_embed(
                movie_info,
                custom_header=f"🎲 Recommended{header_str}:",
                footer_text="Movie Recommendation • Data from TMDB/OMDb • Click title for IMDb"
            )
            view = RecommendView(genre=genre, person_name=person_name)
            await add_watch_button(view, movie_info)
            return {"embed": embed, "view": view}

        if intent == "actor":
            person_name = extract_person(text)
            if not person_name:
                # If extract_person fails, assume the user provided the name directly after "about" or "who is"
                person_name = re.sub(r"^(who is|tell me about|info on|info about|who is in|movies by|movies with)\s+", "", text, flags=re.IGNORECASE).strip(" ?.")
            
            if not person_name or len(person_name) < 3:
                return {"content": "Which actor or director are you looking for?"}
            
            chosen_title = await pick_recommendation(person_name=person_name)
            if not chosen_title:
                return {"content": f"I couldn't find any well-known movies for **{person_name}**."}
                
            movie_info = await fetch_omdb_data(chosen_title)
            if movie_info.get("Response") != "True":
                return {"content": f"Could not load recommendation for '{chosen_title}'."}
                
            embed = build_movie_embed(
                movie_info,
                custom_header=f"⭐ Featuring {person_name.title()}:",
                footer_text="Actor Search • Data from TMDB/OMDb • Click title for IMDb"
            )
            view = RecommendView(person_name=person_name.title())
            await add_watch_button(view, movie_info)
            return {"embed": embed, "view": view}

        if intent == "search":
            title, year = extract_title(text)
            if not title:
                return {"content": "Which movie or show should I look up?"}
            movie_info = await lookup_movie(title, year)
            if movie_info.get("Response") != "True":
                return {"content": f"I couldn't find **{title}**. Try `/movie` with the exact title."}
            canonical_title = f"{movie_info.get('Title')} ({movie_info.get('Year')})"
            view = MovieActionView(movie_title=canonical_title)
            await add_watch_button(view, movie_info)
            return {"embed": build_movie_embed(movie_info), "view": view}

        if intent == "trailer":
            title, year = extract_title(text)
            if not title:
                return {"content": "Which movie's trailer do you want?"}
            canonical_title = await resolve_canonical_title(title, year)
            trailer_url = await fetch_youtube_trailer(canonical_title)
            if trailer_url:
                return {"content": f"🎬 **{canonical_title}** - Official Trailer:\n{trailer_url}"}
            return {"content": f"Could not find a trailer for **{canonical_title}** on YouTube."}

        if intent == "watchlist_admin":
            action = analysis["watchlist_action"]

            # Explicit wording beats the model's guess for which list to show
            if action in ("view_server", "view_personal"):
                if re.search(r"\b(my|mine|personal)\b", text, re.IGNORECASE):
                    action = "view_personal"
                elif re.search(r"\b(our|server|group|everyone'?s?|we)\b", text, re.IGNORECASE):
                    action = "view_server"

            if action == "view_server":
                if not guild_id:
                    return {"content": "The server watchlist only exists inside a server."}
                embed = await server_watchlist_embed(guild_id)
                if not embed:
                    return {"content": "The server watchlist is empty. Ask me to add something!"}
                return {"embed": embed}

            if action == "view_personal":
                embed = await personal_watchlist_embed(user)
                if not embed:
                    return {"content": "Your personal watchlist is empty!", "private": True}
                return {"embed": embed, "private": True}

            if action == "add":
                title, year = extract_title(text)
                if not title:
                    return {"content": "Which movie should I add?"}
                movie_info = await lookup_movie(title, year)
                if movie_info.get("Response") != "True":
                    return {"content": f"I couldn't find **{title}**. Try `/watchlist add` or `/personal add`."}
                canonical_title = f"{movie_info.get('Title')} ({movie_info.get('Year')})"
                # Let the user pick which list with the existing buttons
                return {
                    "content": f"Which watchlist should I add **{canonical_title}** to?",
                    "embed": build_movie_embed(movie_info),
                    "view": MovieActionView(movie_title=canonical_title),
                }

            # Removing/clearing is destructive, so keep it on explicit slash commands
            return {
                "content": (
                    "To change a watchlist, use:\n"
                    "• `/watchlist watched` - mark a server movie as watched\n"
                    "• `/watchlist history` - see what the server has watched\n"
                    "• `/personal remove` - remove from your list\n"
                    "• `/watchlist clear` / `/personal clear` - clear a list"
                )
            }

    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return {"content": "I couldn't reach the movie service. Please try again."}

    # casual / anything else
    return {"content": "👋 Hey there!\n\n" + CHAT_HELP}


def _send_kwargs(result: dict) -> dict:
    """Drop empty values and block pings from echoed user text."""
    kwargs = {k: v for k, v in result.items() if k != "private" and v is not None}
    kwargs["allowed_mentions"] = discord.AllowedMentions.none()
    return kwargs


# Set up the bot and its slash commands
class MovieBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


bot = MovieBot()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Connected to {len(bot.guilds)} server(s). Syncing slash commands...")

    # Instantly sync slash commands to all servers the bot is currently in
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"[OK] Synced {len(synced)} slash command(s) to server '{guild.name}' ({guild.id})")
        except Exception as e:
            print(f"[WARN] Could not sync commands to server '{guild.name}': {e}")

    print("\nBot is live! Commands available in Discord:")
    print(" - /movie [title] [year]")
    print(" - /recommend [genre]")
    print(" - /trailer [movie]")
    print(" - /marathon [franchise]")
    print(" - /watchlist (add/view/watched/history)")
    print(" - /personal (add/view/remove)")
    print(" - /ask [message]  (or @mention / DM the bot in plain English)\n")


@bot.event
async def on_message(message: discord.Message):
    """Answer plain-English messages when the bot is @mentioned or DMed."""
    if message.author.bot:
        return

    is_dm = message.guild is None
    if not is_dm and bot.user not in message.mentions:
        return

    text = re.sub(rf"<@!?{bot.user.id}>", "", message.content).strip()
    if not text:
        await message.reply(CHAT_HELP, mention_author=False)
        return

    async with message.channel.typing():
        result = await handle_natural_request(text, message.author, message.guild.id if message.guild else None)

    # Personal results go to DMs when asked in a public channel
    if result.get("private") and not is_dm:
        try:
            await message.author.send(**_send_kwargs(result))
            await message.reply("📬 I sent that to your DMs.", mention_author=False)
            return
        except discord.Forbidden:
            pass

    await message.reply(**_send_kwargs(result), mention_author=False)


@bot.tree.command(
    name="ask",
    description="Ask the movie bot anything in plain English."
)
@app_commands.describe(message="e.g. 'recommend a scary movie' or 'trailer for Dune'")
async def ask(interaction: discord.Interaction, message: str):
    await interaction.response.defer(thinking=True)

    result = await handle_natural_request(message, interaction.user, interaction.guild_id)

    if result.get("private"):
        # Replace the public "thinking" message with a private one
        await interaction.delete_original_response()
        await interaction.followup.send(**_send_kwargs(result), ephemeral=True)
    else:
        await interaction.followup.send(**_send_kwargs(result))


@bot.tree.command(
    name="movie",
    description="Find a movie or TV show with its poster and ratings."
)
@app_commands.describe(
    title="Movie or TV show title",
    year="Optional release year to help find the right result",
    season="Season number (for TV shows)",
    episode="Episode number (for TV shows)"
)
async def movie(
    interaction: discord.Interaction,
    title: str,
    year: int = None,
    season: int = None,
    episode: int = None
):
    title = title.strip()

    if not title:
        await interaction.response.send_message(
            "Please enter a movie or TV show title.",
            ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)

    try:
        movie_info = await fetch_omdb_data(title, year)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        await interaction.followup.send(
            "I couldn't reach the movie service. Please try again.",
            ephemeral=True
        )
        return

    if movie_info.get("Response") != "True":
        error = movie_info.get("Error", "Movie not found.")
        await interaction.followup.send(
            f"Search unsuccessful: {error}",
            allowed_mentions=discord.AllowedMentions.none()
        )
        return

    custom_header = None
    if movie_info.get("Type") == "series" and (season is not None or episode is not None):
        s = season if season is not None else 1
        e = episode if episode is not None else 1
        custom_header = f"S{s:02d}E{e:02d} -"

    embed = build_movie_embed(movie_info, custom_header=custom_header)
    canonical_title = f"{movie_info.get('Title')} ({movie_info.get('Year')})"
    view = MovieActionView(movie_title=canonical_title)
    await add_watch_button(view, movie_info, season=season, episode=episode)
    
    await interaction.followup.send(embed=embed, view=view)


GENRE_CHOICES = [
    app_commands.Choice(name="🎬 Action", value="action"),
    app_commands.Choice(name="🚀 Sci-Fi", value="sci-fi"),
    app_commands.Choice(name="😂 Comedy", value="comedy"),
    app_commands.Choice(name="🎭 Drama", value="drama"),
    app_commands.Choice(name="👻 Horror", value="horror"),
    app_commands.Choice(name="🎨 Animation", value="animation"),
    app_commands.Choice(name="💥 Thriller", value="thriller"),
    app_commands.Choice(name="💖 Romance", value="romance"),
    app_commands.Choice(name="🔍 Mystery", value="mystery"),
    app_commands.Choice(name="🧙 Fantasy", value="fantasy"),
    app_commands.Choice(name="🎥 Documentary", value="documentary"),
    app_commands.Choice(name="👨‍👩‍👧‍👦 Family", value="family"),
    app_commands.Choice(name="🗺️ Adventure", value="adventure"),
    app_commands.Choice(name="🕵️ Crime", value="crime"),
    app_commands.Choice(name="🌸 Anime", value="anime"),
]


@bot.tree.command(
    name="recommend",
    description="Get a random movie recommendation to watch!"
)
@app_commands.choices(genre=GENRE_CHOICES)
@app_commands.describe(
    genre="Optional genre to filter recommendations"
)
async def recommend(
    interaction: discord.Interaction,
    genre: app_commands.Choice[str] = None
):
    await interaction.response.defer(thinking=True)

    selected_genre = genre.value if genre else None
    chosen_title = await pick_recommendation(selected_genre)

    try:
        movie_info = await fetch_omdb_data(chosen_title)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        await interaction.followup.send(
            "I couldn't reach the movie service. Please try again.",
            ephemeral=True
        )
        return

    if movie_info.get("Response") != "True":
        await interaction.followup.send(
            f"Could not load recommendation for '{chosen_title}'. Please try again.",
            ephemeral=True
        )
        return

    genre_name = genre.name if genre else "All Genres"
    embed = build_movie_embed(
        movie_info,
        custom_header=f"🎲 Recommended [{genre_name}]:",
        footer_text="Movie Recommendation • Data from OMDb • Click title for IMDb"
    )

    view = RecommendView(genre=selected_genre)
    await add_watch_button(view, movie_info)
    await interaction.followup.send(embed=embed, view=view)

@bot.tree.command(
    name="trailer",
    description="Fetch the official YouTube trailer for a movie."
)
@app_commands.describe(title="Movie or TV show title")
async def trailer(interaction: discord.Interaction, title: str):
    await interaction.response.defer()
    
    # Try resolving canonical name using OMDb for better search accuracy
    canonical_title = await resolve_canonical_title(title)
        
    trailer_url = await fetch_youtube_trailer(canonical_title)
    
    if trailer_url:
        await interaction.followup.send(f"🎬 **{canonical_title}** - Official Trailer:\n{trailer_url}")
    else:
        await interaction.followup.send(f"Could not find a trailer for **{canonical_title}** on YouTube.")

# Watchlist Groups
@bot.tree.command(
    name="marathon",
    description="Search OMDB for a franchise/series and add all its movies to the server watchlist."
)
@app_commands.describe(franchise="The name of the franchise or series (e.g., 'Harry Potter', 'Star Wars')")
async def marathon(interaction: discord.Interaction, franchise: str):
    if not interaction.guild_id:
        await interaction.response.send_message("This command can only be used in a server, not in DMs.", ephemeral=True)
        return
        
    await interaction.response.defer()
    
    try:
        movies = await fetch_omdb_search(franchise)
    except Exception as e:
        await interaction.followup.send("An error occurred while fetching movies from OMDb.", ephemeral=True)
        print(f"Error in /marathon fetch: {e}")
        return
    
    if not movies:
        await interaction.followup.send(
            f"Could not find any movies for the franchise '{franchise}'. Try being more specific.",
            ephemeral=True
        )
        return
        
    movies_sorted = sorted(movies, key=lambda m: m.get("Year", "0")[:4])
    
    params_list = []
    added_titles = []
    
    for movie in movies_sorted:
        title = movie.get("Title")
        year = movie.get("Year")
        canonical_title = f"{title} ({year})"
        
        params_list.append((interaction.guild_id, canonical_title, interaction.user.id))
        added_titles.append(f"• {canonical_title}")
        
    if params_list:
        try:
            await async_db_execute_many(
                "INSERT INTO server_watchlist (guild_id, movie_title, added_by) VALUES (?, ?, ?)",
                params_list
            )
        except Exception as e:
            await interaction.followup.send("Failed to save the movies to the database.", ephemeral=True)
            print(f"DB Error in /marathon: {e}")
            return
            
    description = "\n".join(added_titles)
    if len(description) > 4000:
        description = description[:4000] + "\n...and more!"
        
    embed = discord.Embed(
        title=f"🍿 Marathon Started: {franchise}",
        description=description,
        color=discord.Color.brand_red()
    )
    embed.set_footer(text=f"Added {len(params_list)} movies to the server watchlist.")
    
    await interaction.followup.send(embed=embed)


server_group = app_commands.Group(name="watchlist", description="Collaborative server watchlist commands")
personal_group = app_commands.Group(name="personal", description="Personal watchlist commands")

@server_group.command(name="add", description="Add a movie to the server watchlist")
@app_commands.describe(title="Movie title")
async def watchlist_add(interaction: discord.Interaction, title: str):
    await interaction.response.defer()
    
    canonical_title = await resolve_canonical_title(title)
        
    await async_db_query(
        "INSERT INTO server_watchlist (guild_id, movie_title, added_by) VALUES (?, ?, ?)",
        (interaction.guild_id, canonical_title, interaction.user.id)
    )
    await interaction.followup.send(f"✅ Added **{canonical_title}** to the server watchlist!")

@server_group.command(name="view", description="View the server watchlist")
async def watchlist_view(interaction: discord.Interaction):
    await interaction.response.defer()
    
    embed = await server_watchlist_embed(interaction.guild_id)
    
    if not embed:
        await interaction.followup.send("The server watchlist is currently empty. Use `/watchlist add` to add some movies!")
        return
        
    await interaction.followup.send(embed=embed)

@server_group.command(name="watched", description="Mark a movie as watched and move to history")
@app_commands.describe(title="Movie title (exact match from watchlist)")
async def watchlist_watched(interaction: discord.Interaction, title: str):
    await interaction.response.defer()
    
    row = await async_db_query(
        "SELECT id, movie_title FROM server_watchlist WHERE guild_id = ? AND movie_title LIKE ?",
        (interaction.guild_id, f"%{title}%"), fetch=True
    )
    
    if not row:
        await interaction.followup.send(f"Could not find a movie matching **{title}** in the watchlist.")
        return
        
    db_id, actual_title = row
    
    await async_db_query("DELETE FROM server_watchlist WHERE id = ?", (db_id,))
    await async_db_query(
        "INSERT INTO server_history (guild_id, movie_title, marked_by) VALUES (?, ?, ?)",
        (interaction.guild_id, actual_title, interaction.user.id)
    )
    
    await interaction.followup.send(f"✅ Marked **{actual_title}** as watched! It has been moved to the server history.")

@server_group.command(name="history", description="View the server's watched history")
async def watchlist_history(interaction: discord.Interaction):
    await interaction.response.defer()
    
    rows = await async_db_query(
        "SELECT movie_title, watched_at FROM server_history WHERE guild_id = ? ORDER BY watched_at DESC LIMIT 50",
        (interaction.guild_id,), fetchall=True
    )
    
    if not rows:
        await interaction.followup.send("The server history is empty. Mark movies as watched to build your digital diary!")
        return
        
    embed = discord.Embed(title="📜 Server Watched History", color=discord.Color.green())
    
    description = ""
    for i, (m_title, watched_at) in enumerate(rows, 1):
        date_str = watched_at.split(" ")[0]
        description += f"**{i}.** {m_title} *(Watched: {date_str})*\n"
        
    if len(description) > 4000:
        description = description[:4000] + "\n...and more!"
        
    embed.description = description
    await interaction.followup.send(embed=embed)

@server_group.command(name="clear", description="Clear all movies from the server watchlist")
async def watchlist_clear(interaction: discord.Interaction):
    await interaction.response.defer()
    
    await async_db_query(
        "DELETE FROM server_watchlist WHERE guild_id = ?",
        (interaction.guild_id,)
    )
    
    await interaction.followup.send("✅ The server watchlist has been completely cleared!")

@personal_group.command(name="add", description="Add a movie to your personal watchlist")
@app_commands.describe(title="Movie title")
async def personal_add(interaction: discord.Interaction, title: str):
    await interaction.response.defer(ephemeral=True)
    
    canonical_title = await resolve_canonical_title(title)
        
    await async_db_query(
        "INSERT INTO personal_watchlist (user_id, movie_title) VALUES (?, ?)",
        (interaction.user.id, canonical_title)
    )
    
    await interaction.followup.send(f"✅ Added **{canonical_title}** to your personal watchlist!")

@personal_group.command(name="view", description="View your personal watchlist")
async def personal_view(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    embed = await personal_watchlist_embed(interaction.user)
    
    if not embed:
        await interaction.followup.send("Your personal watchlist is empty!")
        return
        
    await interaction.followup.send(embed=embed)

@personal_group.command(name="remove", description="Remove a movie from your personal watchlist")
@app_commands.describe(title="Movie title")
async def personal_remove(interaction: discord.Interaction, title: str):
    await interaction.response.defer(ephemeral=True)
    
    row = await async_db_query(
        "SELECT id, movie_title FROM personal_watchlist WHERE user_id = ? AND movie_title LIKE ?",
        (interaction.user.id, f"%{title}%"), fetch=True
    )
    
    if not row:
        await interaction.followup.send(f"Could not find **{title}** in your watchlist.")
        return
        
    db_id, actual_title = row
    await async_db_query("DELETE FROM personal_watchlist WHERE id = ?", (db_id,))
    
    await interaction.followup.send(f"✅ Removed **{actual_title}** from your watchlist.")

@personal_group.command(name="clear", description="Clear all movies from your personal watchlist")
async def personal_clear(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    await async_db_query(
        "DELETE FROM personal_watchlist WHERE user_id = ?",
        (interaction.user.id,)
    )
    
    await interaction.followup.send("✅ Your personal watchlist has been completely cleared!")

bot.tree.add_command(server_group)
bot.tree.add_command(personal_group)

bot.run(DISCORD_TOKEN)

