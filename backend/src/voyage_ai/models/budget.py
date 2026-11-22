from datetime import date
from math import isfinite
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


BudgetCategory = Literal[
    "transportation",
    "accommodation",
    "food_dining",
    "local_transportation",
    "activities_attractions",
    "contingency",
]

PricingBasis = Literal[
    "per_trip",
    "per_traveler",
    "per_day",
    "per_night",
    "per_traveler_per_day",
    "per_traveler_per_night",
    "per_room_per_night",
    "per_capsule_per_night",
    "per_person_per_room_per_night",
    "per_ride",
    "per_admission",
]

# ISO 4217 currencies commonly encountered in international travel prices.
ISO_4217_CURRENCY_CODES = frozenset((
    "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BOV BRL BSD BTN BWP BYN BZD"
    " CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP"
    " GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW"
    " KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN"
    " NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD"
    " SHP SLE SLL SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU"
    " UYW UZS VED VES VND VUV WST XAF XAG XAU XBA XBB XBC XBD XCD XDR XOF XPD XPF XPT XSU XTS XUA XXX YER"
    " ZAR ZMW ZWL"
).split())

SUPPORTED_COST_CURRENCIES = frozenset({
    "AED", "ARS", "AUD", "BDT", "BHD", "BRL", "CAD", "CHF", "CLP", "CNY",
    "COP", "CZK", "DKK", "EGP", "EUR", "FJD", "GBP", "GHS", "HKD", "HUF",
    "IDR", "ILS", "INR", "ISK", "JOD", "JPY", "KES", "KHR", "KRW", "KWD",
    "LKR", "MAD", "MMK", "MNT", "MOP", "MUR", "MXN", "MYR", "NAD", "NGN",
    "NOK", "NPR", "NZD", "OMR", "PEN", "PHP", "PKR", "PLN", "QAR", "RON",
    "RSD", "RUB", "SAR", "SEK", "SGD", "THB", "TND", "TRY", "TWD", "TZS",
    "UAH", "UGX", "USD", "UYU", "UZS", "VND", "XOF", "XPF", "ZAR",
})

CostCertainty = Literal["estimated", "confirmed"]
CostSourceType = Literal["official", "third_party", "unknown"]


class BudgetCostEstimate(BaseModel):
    """A sourced category cost. Amount is in the trip currency."""

    category: BudgetCategory
    scope: Literal["category", "entity", "manual"] = "category"
    entity_name: str | None = None
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    amount: float = Field(ge=0)
    amount_min: float | None = Field(default=None, ge=0)
    amount_max: float | None = Field(default=None, ge=0)
    currency: str = Field(min_length=3, max_length=3)
    basis: PricingBasis = "per_trip"
    fare_class: Literal["adult", "child"] | None = None
    taxes_included: bool | None = None
    traveler_count_override: int | None = Field(default=None, ge=1)
    quantity_override: int | None = Field(default=None, ge=1)
    certainty: CostCertainty = "estimated"
    source: str = Field(min_length=1)
    source_url: str | None = None
    retrieved_on: date | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_level: Literal["low", "medium", "high"] = "low"
    source_type: CostSourceType = "unknown"
    evidence_quote: str | None = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("Cost amount must be finite.")
        return round(value, 2)

    @field_validator("amount_min", "amount_max")
    @classmethod
    def range_amounts_must_be_finite(cls, value: float | None) -> float | None:
        if value is not None:
            if not isfinite(value):
                raise ValueError("Cost range must be finite.")
            return round(value, 2)
        return value

    @model_validator(mode="after")
    def validate_amount_range(self):
        low = self.amount if self.amount_min is None else self.amount_min
        high = self.amount if self.amount_max is None else self.amount_max
        if low > high:
            raise ValueError("Cost range minimum cannot exceed its maximum.")
        if abs(high - self.amount) > 0.01:
            raise ValueError("Cost amount must equal the conservative range maximum.")
        return self

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in ISO_4217_CURRENCY_CODES:
            raise ValueError(f"Unknown ISO 4217 cost currency: {normalized}.")
        return normalized


class BudgetCategoryAllocation(BaseModel):
    category: BudgetCategory
    label: str
    allocated_amount: float = Field(ge=0)
    known_cost_estimate: float | None = Field(default=None, ge=0)
    known_cost_estimate_min: float | None = Field(default=None, ge=0)
    certainty: CostCertainty | Literal["unavailable"] = "unavailable"
    sources: list[str] = Field(default_factory=list)
    cost_evidence: list[BudgetCostEstimate] = Field(default_factory=list)

    @field_validator("allocated_amount", "known_cost_estimate", "known_cost_estimate_min")
    @classmethod
    def amounts_must_be_finite(cls, value: float | None) -> float | None:
        if value is not None:
            if not isfinite(value):
                raise ValueError("Budget values must be finite.")
            return round(value, 2)
        return value


class BudgetAllocation(BaseModel):
    origin: str
    destination: str
    total_budget: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    travelers: int = Field(ge=1, le=20)
    trip_days: int = Field(ge=1)
    contingency_rate: float = Field(ge=0, le=1)
    categories: list[BudgetCategoryAllocation]
    unallocated_balance: float = Field(ge=0)
    edited_categories: list[BudgetCategory] = Field(default_factory=list)
    allocation_note: str

    @field_validator("total_budget", "unallocated_balance", "contingency_rate")
    @classmethod
    def monetary_values_must_be_finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("Budget values must be finite.")
        return round(value, 2)

    @model_validator(mode="after")
    def validate_allocation(self):
        expected = {
            "transportation",
            "accommodation",
            "food_dining",
            "local_transportation",
            "activities_attractions",
            "contingency",
        }
        actual = [category.category for category in self.categories]
        if len(actual) != len(expected) or set(actual) != expected:
            raise ValueError("Allocation must contain each budget category exactly once.")

        allocated = sum(category.allocated_amount for category in self.categories)
        if allocated > self.total_budget + 0.01:
            raise ValueError("Category allocations exceed the total trip budget.")
        expected_remaining = round(self.total_budget - allocated, 2)
        if abs(self.unallocated_balance - expected_remaining) > 0.01:
            raise ValueError("Unallocated balance does not match the category allocations.")
        return self

    def amount_for(self, category: BudgetCategory) -> float:
        return next(item.allocated_amount for item in self.categories if item.category == category)
