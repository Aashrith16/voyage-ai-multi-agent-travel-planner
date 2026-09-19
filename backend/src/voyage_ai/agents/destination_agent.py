from dotenv import load_dotenv
from google import genai

from voyage_ai.models.destination import (
    DestinationAnalysis,
    DestinationResearch,
    ResearchSource,
)
from voyage_ai.models.trip import TripRequest
from voyage_ai.tools.web_search import (
    search_destination,
)


load_dotenv()


client = genai.Client()


SYSTEM_INSTRUCTIONS = """
You are the Destination Research Agent for VoyageAI.

Your task is to analyze destination information gathered
from web search and recommend places relevant to the traveler.

Important rules:

1. Use ONLY the evidence supplied in WEB SEARCH SOURCES.

2. Do not invent attractions, facts, prices, opening hours,
   addresses, or URLs.

3. Prioritize recommendations matching the traveler's interests.

4. Keep recommendations useful and specific.

5. Every recommendation must contain at least one source_id.

6. source_ids must refer only to IDs that appear in the supplied
   WEB SEARCH SOURCES.

7. Do not generate URLs yourself.

8. Do not search for flights or hotels.

9. Do not create the full itinerary yet.

10. If the supplied evidence does not support a claim,
    do not make that claim.
"""


def research_destination(
    trip: TripRequest,
) -> DestinationResearch:
    """
    Research a travel destination using Tavily
    and analyze the evidence using Gemini.
    """

    # ---------------------------------------------
    # STEP 1
    # Search the live web
    # ---------------------------------------------

    sources = search_destination(
        destination=trip.destination,
        interests=trip.interests,
    )


    # ---------------------------------------------
    # STEP 2
    # Convert sources into evidence for Gemini
    # ---------------------------------------------

    evidence_blocks = []

    for source in sources:

        evidence_blocks.append(
            f"""
SOURCE ID: {source["id"]}

TITLE:
{source["title"]}

CONTENT:
{source["content"]}
"""
        )

    evidence = "\n".join(
        evidence_blocks
    )


    # ---------------------------------------------
    # STEP 3
    # Create prompt
    # ---------------------------------------------

    prompt = f"""
{SYSTEM_INSTRUCTIONS}

TRAVELER INFORMATION

Destination:
{trip.destination}

Traveler interests:
{trip.interests}

RECOMMENDATION REQUIREMENTS

Generate between 16 and 20 distinct, realistic activity recommendations
for the destination.

The recommendations must provide enough options for a multi-day itinerary.

Include a balanced variety of:
- famous attractions and landmarks
- places strongly related to the traveler's interests
- cultural and historical attractions
- local food experiences
- shopping areas
- indoor activities
- outdoor activities
- evening or nightlife experiences where appropriate
- local neighborhoods or less-obvious experiences

Important rules:
- Recommend real, identifiable places or activities.
- Avoid duplicates and near-duplicates.
- Do not recommend the same district repeatedly under slightly different names.
- Prefer places that can realistically be resolved to geographic coordinates.
- Spread recommendations across different parts of the destination when useful.
- Every recommendation must include a clear reason for recommendation.
- Every recommendation must reference only valid source IDs from the provided web search evidence.
- Do not invent source IDs.
- Do not invent a place simply to reach the requested number of recommendations.
- The `name` of every recommendation MUST be the canonical name of one real,
  geographically identifiable place that can be searched on a map.

- The `name` must represent a single venue, landmark, district, park, museum,
  market, attraction, restaurant, shopping complex, station, or other physical
  place.

- Do NOT put tour titles, workshop titles, classes, guided experiences,
  generic categories, or descriptive activity phrases in the `name`.

- Do NOT use transport networks or entire train lines such as "Yamanote Line"
  as recommendation names.

- If recommending a tour, workshop, food experience, or similar activity,
  use the real physical venue or meeting location as the recommendation name
  and describe the experience in `why_recommended`.

- Prefer official/canonical place names that a geocoder is likely to recognize.

Examples:

BAD name:
"Akihabara Anime & Gaming Adventure Tour"

GOOD name:
"Akihabara"

BAD name:
"Manga Drawing Workshop Guided by Pro Manga Artist"

GOOD name:
"Manga School Nakano"

BAD name:
"Yamanote Line"

GOOD name:
"Tokyo Station"


WEB SEARCH SOURCES

{evidence}
"""


    # ---------------------------------------------
    # STEP 4
    # Gemini analyzes grounded evidence
    # ---------------------------------------------

    interaction = client.interactions.create(
        model="gemini-3.5-flash-lite",
        input=prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": DestinationAnalysis.model_json_schema(),
        },
    )


    analysis = DestinationAnalysis.model_validate_json(
        interaction.output_text
    )


    # ---------------------------------------------
    # STEP 5
    # Validate source IDs
    # ---------------------------------------------

    valid_source_ids = {
        source["id"]
        for source in sources
    }

    for recommendation in analysis.recommendations:

        invalid_ids = (
            set(recommendation.source_ids)
            - valid_source_ids
        )

        if invalid_ids:
            raise ValueError(
                "Gemini returned invalid source IDs: "
                f"{invalid_ids}"
            )


    # ---------------------------------------------
    # STEP 6
    # Attach REAL source URLs using Python
    # ---------------------------------------------

    research_sources = [
        ResearchSource(
            id=source["id"],
            title=source["title"],
            url=source["url"],
        )
        for source in sources
    ]


    return DestinationResearch(
        destination=analysis.destination,
        summary=analysis.summary,
        recommendations=analysis.recommendations,
        practical_tips=analysis.practical_tips,
        sources=research_sources,
    )