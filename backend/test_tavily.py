import os

from dotenv import load_dotenv
from tavily import TavilyClient


# Load variables from .env
load_dotenv()


# Read your Tavily API key from .env
client = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)


# Search the live web
response = client.search(
    query="Best attractions in Tokyo for anime, technology and food lovers",
    search_depth="basic",
    max_results=5,
)


# Print the results
print("\n--- TAVILY SEARCH RESULTS ---")

for result in response["results"]:
    print("\nTITLE:")
    print(result["title"])

    print("\nURL:")
    print(result["url"])

    print("\nCONTENT:")
    print(result["content"])

    print("-" * 60)