# Import necessary libraries
import os

import requests
from dotenv import load_dotenv

# Read your API key from .env
load_dotenv()
api_key = os.getenv("OMDB_API_KEY")

# Display a welcome message
print("Welcome to Movie_TV Search!")

# Keep searching until the user chooses to quit
while True:
    movie_title = input(
        "\nEnter a movie title (or type quit): "
    ).strip()

    # Stop the loop if the user types quit
    if movie_title.lower() == "quit":
        print("Thanks for using Movie_TV Search!")
        break

    # Ask again if the user leaves the title blank
    if movie_title == "":
        print("Please enter a movie title.")
        continue

    print("You searched for:", movie_title)

    # Prepare the information OMDb needs
    params = {
        "t": movie_title,
        "apikey": api_key
    }

    # Send the request to OMDb
    print("Searching for movie information...")

    response = requests.get(
        "https://www.omdbapi.com/",
        params=params,
        timeout=10
    )

    # Convert the response into a Python dictionary
    movie_info = response.json()

    # Check if the movie was found
    if movie_info.get("Response") == "True":
        print("Title:", movie_info.get("Title"))
        print("Year:", movie_info.get("Year"))
        print("Rated:", movie_info.get("Rated"))
        print("Released:", movie_info.get("Released"))
        print("Runtime:", movie_info.get("Runtime"))
        print("Genre:", movie_info.get("Genre"))
        print("Director:", movie_info.get("Director"))
        print("Writer:", movie_info.get("Writer"))
        print("Actors:", movie_info.get("Actors"))
        print("Plot:", movie_info.get("Plot"))
        print("Language:", movie_info.get("Language"))
        print("Country:", movie_info.get("Country"))
        print("Awards:", movie_info.get("Awards"))

        rating = movie_info.get("imdbRating", "N/A")

        if rating == "N/A":
            print("IMDb Rating: Not available")
        else:
            print("IMDb Rating:", rating, "/ 10")

    # Display the reason the search failed
    else:
        print(
            "Search unsuccessful:",
            movie_info.get("Error", "Data not found.")
        )
