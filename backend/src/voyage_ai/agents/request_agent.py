from dotenv import load_dotenv
from google import genai

from voyage_ai.models.trip import TripRequestDraft


# Load GEMINI_API_KEY from .env
load_dotenv()


# Fields that must eventually exist before
# VoyageAI can create a complete trip.
REQUIRED_TRIP_FIELDS = [
    "origin",
    "destination",
    "departure_date",
    "return_date",
    "travelers",
    "budget",
]


# Create the Gemini client.
client = genai.Client()


SYSTEM_INSTRUCTIONS = """
You are the Request Understanding Agent for VoyageAI.

Your only job is to convert a user's natural-language
travel request into structured travel information.

Rules:

1. Extract only information explicitly provided by the user.

2. Never invent missing information.

3. Extract the origin city only if the user provides it.

4. Extract the destination only if the user provides it.

5. Extract exact departure and return dates only when
   they are clearly provided.

6. If the user gives vague dates such as:
   - next month
   - sometime in December
   - next summer
   - during Diwali
   do NOT invent exact dates.
   Leave departure_date and/or return_date empty.

7. Extract the traveler count only if the user provides it.

8. Extract the budget only if the user provides it.

9. If the user explicitly mentions a currency, extract it.
   If no currency is mentioned, leave currency empty.
   Do not guess the currency.

10. Extract interests and preferences only when clearly
    mentioned by the user.

11. Do NOT recommend flights.

12. Do NOT recommend hotels.

13. Do NOT recommend activities.

14. Do NOT search the web.

15. Do NOT perform itinerary planning yet.

Your responsibility at this stage is ONLY information extraction.
"""


def understand_trip_request(user_input: str) -> TripRequestDraft:
    """
    Convert a natural-language travel request into
    structured TripRequestDraft data.
    """

    prompt = f"""
{SYSTEM_INSTRUCTIONS}

USER REQUEST:

{user_input}
"""

    interaction = client.interactions.create(
        model="gemini-3.5-flash-lite",
        input=prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": TripRequestDraft.model_json_schema(),
        },
    )

    # Gemini returns JSON text.
    # Pydantic converts and validates that JSON.
    draft = TripRequestDraft.model_validate_json(
        interaction.output_text
    )

    # Python calculates missing fields deterministically.
    draft.missing_fields = [
        field
        for field in REQUIRED_TRIP_FIELDS
        if getattr(draft, field) is None
    ]

    return draft

FIELD_QUESTIONS = {
    "origin": "Where will you be traveling from?",
    "destination": "Where would you like to travel?",
    "departure_date": "What is your exact departure date?",
    "return_date": "What is your exact return date?",
    "travelers": "How many people will be traveling?",
    "budget": "What is your approximate total budget?",
}


def get_clarification_questions(
    draft: TripRequestDraft,
) -> list[str]:
    """
    Create user-friendly questions for missing trip details.
    """

    return [
        FIELD_QUESTIONS[field]
        for field in draft.missing_fields
        if field in FIELD_QUESTIONS
    ]