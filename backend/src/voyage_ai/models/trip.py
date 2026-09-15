from datetime import date

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)


# --------------------------------------------------
# CURRENCY NORMALIZATION
# Add this directly BELOW the imports
# and ABOVE TripRequestDraft
# --------------------------------------------------

CURRENCY_ALIASES = {
    "inr": "INR",
    "rupee": "INR",
    "rupees": "INR",
    "indian rupee": "INR",
    "indian rupees": "INR",
    "rs": "INR",
    "₹": "INR",

    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "us dollar": "USD",
    "us dollars": "USD",
    "$": "USD",

    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "€": "EUR",

    "jpy": "JPY",
    "yen": "JPY",
    "japanese yen": "JPY",
    "¥": "JPY",
}


def normalize_currency(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip().lower()

    return CURRENCY_ALIASES.get(
        cleaned,
        value.strip().upper(),
    )


# --------------------------------------------------
# DRAFT MODEL
# --------------------------------------------------

class TripRequestDraft(BaseModel):
    origin: str | None = None
    destination: str | None = None

    departure_date: date | None = None
    return_date: date | None = None

    travelers: int | None = Field(
        default=None,
        ge=1,
        le=20,
    )

    budget: float | None = Field(
        default=None,
        gt=0,
    )

    currency: str | None = None

    interests: list[str] = Field(
        default_factory=list,
    )

    missing_fields: list[str] = Field(
        default_factory=list,
    )

    # Add this INSIDE TripRequestDraft
    # after the fields
    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency_field(cls, value):
        return normalize_currency(value)


# --------------------------------------------------
# FINAL MODEL
# --------------------------------------------------

class TripRequest(BaseModel):
    origin: str
    destination: str

    departure_date: date
    return_date: date

    travelers: int = Field(
        ge=1,
        le=20,
    )

    budget: float = Field(
        gt=0,
    )

    currency: str = "INR"

    interests: list[str] = Field(
        default_factory=list,
    )

    # Add the SAME currency validator
    # inside TripRequest
    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency_field(cls, value):
        return normalize_currency(value)

    # Keep your existing date validator below it
    @model_validator(mode="after")
    def validate_dates(self):
        if self.return_date <= self.departure_date:
            raise ValueError(
                "Return date must be after departure date."
            )

        return self