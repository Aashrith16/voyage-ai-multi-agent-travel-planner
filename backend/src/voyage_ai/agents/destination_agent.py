import logging

from dotenv import load_dotenv
from google import genai
from pydantic import ValidationError

from voyage_ai.gemini_config import get_gemini_model
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
logger = logging.getLogger(__name__)


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

11. Recommend sightseeing, food, culture, nature, shopping, or other
    visitor activities. Do not include ordinary hotels, hostels, or
    lodging listings as activities. Use a specific place category.
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
    ) or []
    sources = [
        source for source in sources
        if isinstance(source, dict)
        and isinstance(source.get("id"), int)
        and not isinstance(source.get("id"), bool)
        and all(isinstance(source.get(field), str) for field in ("title", "url", "content"))
        and source["title"].strip()
        and source["url"].strip()
        and source["content"].strip()
    ]


    valid_source_ids = {
        source["id"]
        for source in sources
        if isinstance(source.get("id"), int) and not isinstance(source.get("id"), bool)
    }

    research_sources = [
        ResearchSource(id=source["id"], title=source["title"], url=source["url"])
        for source in sources
        if isinstance(source.get("id"), int)
        and not isinstance(source.get("id"), bool)
        and source["id"] in valid_source_ids
    ]

    if not valid_source_ids:
        logger.warning(
            "Destination research has no usable sources; returning incomplete evidence "
            "(source_count=%d)",
            len(sources),
        )
        return DestinationResearch(
            destination=trip.destination,
            summary="Destination research is incomplete because no verifiable search sources were available.",
            recommendations=[],
            practical_tips=[],
            sources=[],
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
- Provide `estimated_visit_minutes` as an approximate planning estimate for the
  specific place, based on its nature and the supplied evidence. This is a
  planning estimate, not an official or verified visit duration. Do not use it
  to imply opening hours or guaranteed visit length. Use null if a reasonable
  estimate cannot be made.
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

    # Gemini can occasionally emit IDs outside the supplied evidence set.
    # Retry once with the exact allowlist, then keep only recommendations whose
    # original source associations resolve to real search results.
    retry_prompt = (
        f"{prompt}\n\nCORRECTION: The only allowed source IDs are "
        f"{sorted(valid_source_ids)}. Recreate the analysis using only these IDs. "
        "Omit any recommendation that cannot be supported by one or more of them. "
        "Do not invent, renumber, or substitute source IDs."
    )
    analysis = None
    final_invalid_ids: set[int] = set()
    parse_failed = False

    for attempt in range(2):
        try:
            interaction = client.interactions.create(
                model=get_gemini_model(),
                input=prompt if attempt == 0 else retry_prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": DestinationAnalysis.model_json_schema(),
                },
            )
            candidate = DestinationAnalysis.model_validate_json(interaction.output_text)
        except ValidationError as error:
            # A malformed structured response, including a non-integer source
            # ID, is eligible for one correction attempt. Provider errors remain
            # visible to the normal workflow error handling.
            parse_failed = True
            logger.warning(
                "Destination research response failed schema validation "
                "(attempt=%d, error_type=%s)",
                attempt + 1,
                type(error).__name__,
            )
            continue

        invalid_ids = {
            source_id
            for recommendation in candidate.recommendations
            for source_id in recommendation.source_ids
            if source_id not in valid_source_ids
        }
        if not invalid_ids:
            analysis = candidate
            parse_failed = False
            break

        final_invalid_ids = invalid_ids
        parse_failed = False
        logger.warning(
            "Destination research returned source IDs outside current search results "
            "(attempt=%d, invalid_ids=%s, valid_source_ids=%s)",
            attempt + 1,
            sorted(invalid_ids),
            sorted(valid_source_ids),
        )

    if analysis is None and not parse_failed and final_invalid_ids:
        # Preserve only exact, valid model-to-source associations. Never
        # reassign a citation or show free-form summary/tips after this fallback.
        last_response = DestinationAnalysis.model_validate_json(interaction.output_text)
        supported_recommendations = []
        for recommendation in last_response.recommendations:
            accepted_ids = [
                source_id for source_id in recommendation.source_ids
                if source_id in valid_source_ids
            ]
            if accepted_ids:
                supported_recommendations.append(
                    recommendation.model_copy(update={"source_ids": accepted_ids})
                )
        analysis = DestinationAnalysis(
            destination=trip.destination,
            summary="Destination research is incomplete; some generated claims did not reference available sources.",
            recommendations=supported_recommendations,
            practical_tips=[],
        )
    elif analysis is None:
        logger.warning(
            "Destination research response remained malformed after one correction attempt "
            "(valid_source_count=%d)",
            len(valid_source_ids),
        )
        analysis = DestinationAnalysis(
            destination=trip.destination,
            summary="Destination research is incomplete because a verifiable structured response was unavailable.",
            recommendations=[],
            practical_tips=[],
        )


    return DestinationResearch(
        destination=trip.destination,
        summary=analysis.summary,
        recommendations=analysis.recommendations,
        practical_tips=analysis.practical_tips,
        sources=research_sources,
    )
