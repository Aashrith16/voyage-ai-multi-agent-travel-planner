import os

from dotenv import load_dotenv
from tavily import TavilyClient


load_dotenv()


client = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)


def search_destination(
    destination: str,
    interests: list[str],
    max_results: int = 6,
) -> list[dict]:
    """
    Search the web for destination information
    relevant to the user's interests.
    """

    if interests:
        interest_text = ", ".join(interests)
    else:
        interest_text = "top attractions and travel experiences"

    query = (
        f"{destination} travel guide best places "
        f"for {interest_text}"
    )

    response = client.search(
        query=query,
        search_depth="basic",
        max_results=max_results,
    )

    sources = []

    for index, result in enumerate(
        response["results"],
        start=1,
    ):
        sources.append(
            {
                "id": index,
                "title": result["title"],
                "url": result["url"],
                "content": result["content"],
            }
        )

    return sources