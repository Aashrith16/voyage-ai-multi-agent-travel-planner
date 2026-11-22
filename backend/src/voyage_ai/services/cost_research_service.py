"""Tavily-backed travel cost research with price-level evidence."""
from datetime import date
from hashlib import sha256
import re
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from voyage_ai.models.activity import ActivityIntelligence
from voyage_ai.models.budget import (
    BudgetCostEstimate,
    ISO_4217_CURRENCY_CODES,
    SUPPORTED_COST_CURRENCIES,
)
from voyage_ai.models.cost_research import (
    CostPriceStatement,
    CostEvidenceOption,
    CostResearchCategory,
    CostResearchResult,
    CostResearchSource,
    VerifiedFreeAdmissionEvidence,
)
from voyage_ai.models.trip import TripRequest
from voyage_ai.tools.web_search import search_trip_costs


_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?"
_CURRENCY_TOKEN = r"(?:[A-Z]{3}|Japanese\s+yen|yen|\$|\u00a3|\u20ac|\u00a5|\u20b9)"
_PRICE_RE = re.compile(
    rf"(?<![\w])(?:(?P<before>{_CURRENCY_TOKEN})\s*)?"
    rf"(?P<low>{_NUMBER})"
    rf"(?:\s*(?:-|\u2013|to)\s*(?:(?P<range_currency>{_CURRENCY_TOKEN})\s*)?(?P<high>{_NUMBER}))?"
    rf"\s*(?P<after>{_CURRENCY_TOKEN})?(?![\w])",
    re.IGNORECASE,
)
_UNLABELED_NUMBER_RE = re.compile(rf"(?<![\w])(?P<amount>{_NUMBER})(?![\w])")
_DIRECT_PRICE_LABEL = re.compile(
    r"(?:price|cost|fee|fare|ticket|admission|rate)\s*(?:is|of|was|around|about|approx(?:imately)?|:|=)?\s*$",
    re.I,
)
_GENERIC_TRIP_TOTAL = re.compile(
    r"\b(?:total|overall|estimated)\s+(?:trip|day\s+trip|vacation|holiday|travel)\s+(?:cost|budget|spend)\b|"
    r"\btotal\s+budget\b|\bday\s+trip\s+cost\b",
    re.I,
)
_AGGREGATE_PRICE = re.compile(r"\b(?:totals?|combined\s+total|grand\s+total)\b", re.I)
_ILLUSTRATIVE_CONTEXT = re.compile(
    r"\b(?:for example|e\.g\.|suppose|hypothetical(?:ly)?|illustrative|sample calculation|worked example|"
    r"works? out at|falls? in the .*?band)\b",
    re.I,
)
_TAX_AMOUNT_CONTEXT = re.compile(
    r"\b(?:(?:accommodation|lodging|hotel|city|municipal|consumption)\s+tax\s*(?:amount)?\s*(?:costs?|of|is|at|:|=)?|"
    r"tax\s+(?:amount|charge|levy)\s*(?:of|is|:|=)?|levy\s+(?:amount|of|is|:|=))\s*$|"
    r"\b(?:accommodation|lodging|hotel|city|municipal|consumption)\s+tax\s+(?:of|is|at)\b|"
    r"\b(?:tax|levy)\s+(?:amount|charge)\s*(?:of|is|:|=)",
    re.I,
)
_PRICE_CONTEXT = re.compile(
    r"price|cost|fee|fare|rate|pass|admission|admit|entrance|entry|ticket|"
    r"per\s+(?:person|travell?er|night|day|ride|adult|child)", re.IGNORECASE,
)
_NON_PRICE_UNIT = re.compile(r"\b(?:am|pm|minutes?|hours?|km|kilomet(?:er|re)s?|years?)\b", re.I)


def _has_explicit_currency_token(match: re.Match[str]) -> bool:
    for name in ("before", "range_currency", "after"):
        token = match.group(name)
        if not token:
            continue
        if token.casefold() in {"yen", "japanese yen"} or token in {"$", "£", "€", "¥", "₹"}:
            return True
        # Currency codes are conventionally uppercase. The price regex is
        # case-insensitive for yen words, so don't misread "The" as a code.
        if len(token) == 3 and token.isalpha() and token == token.upper():
            return True
    return False

_CATEGORY_TERMS: dict[CostResearchCategory, tuple[str, ...]] = {
    "transportation": ("flight", "airfare", "air fare", "train fare", "rail fare", "bus fare", "transport fare", "ticket price"),
    "accommodation": ("hotel", "hostel", "accommodation", "lodging", "room rate", "guesthouse", "ryokan"),
    "food_dining": ("food", "meal", "dining", "restaurant", "lunch", "dinner", "breakfast"),
    "local_transportation": ("local transport", "transit", "metro", "subway", "city bus", "taxi", "day pass", "fare", "transportation ticket"),
    "activities_attractions": ("admission", "attraction", "entrance fee", "entry fee", "ticket", "temple", "museum", "shrine"),
}

_BASIS_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("per_person_per_room_per_night", re.compile(r"per\s+(?:person|travell?er)\s+per\s+room\s+per\s+night", re.I)),
    ("per_room_per_night", re.compile(r"per\s+room\s+per\s+night|per\s+room\s+nightly", re.I)),
    ("per_capsule_per_night", re.compile(r"per\s+capsule\s+per\s+night|per\s+capsule\s+nightly", re.I)),
    ("per_person_per_night", re.compile(r"per\s+(?:person|travell?er|adult|child)\s+per\s+night|per\s+night\s+per\s+(?:person|travell?er)", re.I)),
    ("per_person_per_day", re.compile(r"per\s+(?:person|travell?er|adult|child)\s+per\s+day|per\s+day\s+per\s+(?:person|travell?er)", re.I)),
    ("per_ride", re.compile(r"per\s+ride|each\s+ride|single\s+ride|one\s+ride|per\s+trip\s+on\s+(?:the\s+)?(?:bus|subway|train)", re.I)),
    ("per_admission", re.compile(r"per\s+(?:admission|ticket)|each\s+(?:admission|ticket)", re.I)),
    ("per_night", re.compile(r"per\s+night|nightly|each\s+night", re.I)),
    ("per_day", re.compile(r"per\s+day|daily\s+(?:rate|cost|fare|pass|price)|one.day pass|day pass|valid for one day", re.I)),
    ("per_person", re.compile(r"per\s+(?:person|travell?er|passenger|adult|child)", re.I)),
    ("per_trip", re.compile(r"per\s+trip|round\s+trip|return\s+fare|per\s+journey", re.I)),
)


def _category_queries(trip: TripRequest, activities: ActivityIntelligence | None) -> list[tuple[CostResearchCategory, str]]:
    origin = trip.origin
    destination = trip.destination
    destination_city = destination.split(",", 1)[0].strip()
    dates = f"Dates {trip.departure_date} to {trip.return_date}; {trip.travelers} travellers."
    activity_names = ", ".join(a.name for a in (activities.activities if activities else [])[:8])
    return [
        ("transportation", f"[CATEGORY:transportation] Published fare price range for travel from {origin} to {destination}: airfare, rail or bus fares, currency code and exact per-traveller or round-trip basis. Prefer carrier/operator fare pages. {dates}"),
        ("accommodation", f"[CATEGORY:accommodation] Published {destination_city} accommodation price for a named hotel, ryokan, room or capsule; exact currency and explicit per-room/per-person/per-capsule nightly basis; state taxes and fees. Prefer official property pricing pages. {dates}"),
        ("food_dining", f"[CATEGORY:food_dining] Published {destination_city} restaurant menu or food cost, exact price and per-person/per-meal or per-person/per-day basis. Prefer restaurant menus and official local sources. {dates}"),
        ("local_transportation", f"[CATEGORY:local_transportation] site:kyoto.travel OR site:city.kyoto.lg.jp {destination_city} City Bus {destination_city} Municipal Transportation Bureau subway single fare one-day pass multi-day pass adult child JPY official price. Prefer operator pages; exclude all other cities."),
        ("activities_attractions", f"[CATEGORY:activities_attractions] {destination} official attraction admission entrance ticket prices JPY for {activity_names or 'named local attractions'}; exact named attraction and per-admission basis. Prefer attraction operator websites. {dates}"),
    ]


def _canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    kept_query = "&".join(
        item for item in parts.query.split("&")
        if item and not item.casefold().startswith(("utm_", "fbclid=", "gclid="))
    )
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), parts.path.rstrip("/"), kept_query, ""))


def _source_type(url: str) -> str:
    host = (urlsplit(url).hostname or "").casefold().rstrip(".")
    if host.endswith((".gov", ".go.jp", ".lg.jp")) or ".gov." in host:
        return "official"
    return "third_party" if host else "unknown"


def _has_category_context(text: str, category: CostResearchCategory) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in _CATEGORY_TERMS[category])


def _destination_mentioned(text: str, trip: TripRequest, activities: ActivityIntelligence | None) -> bool:
    lowered = text.casefold()
    destination_city = trip.destination.split(",", 1)[0].strip().casefold()
    if destination_city and destination_city in lowered:
        return True
    if activities and any(activity.name.casefold() in lowered for activity in activities.activities[:8]):
        return True
    return False


def _statement_destination_mentioned(
    title: str,
    context: str,
    trip: TripRequest,
    activities: ActivityIntelligence | None,
) -> bool:
    city = trip.destination.split(",", 1)[0].strip()
    context_lower = context.casefold()
    other_japanese_cities = ("tokyo", "osaka", "nagoya", "sapporo", "fukuoka", "nara", "kobe")
    named_other_cities = [place for place in other_japanese_cities if place != city.casefold() and re.search(rf"\b{place}\b", context_lower)]
    if named_other_cities and city.casefold() in context_lower:
        # A source that places multiple cities in one local price statement
        # cannot establish which city's price the amount belongs to.
        return False
    if _destination_mentioned(context, trip, activities):
        return True
    title_lower = title.casefold()
    if (
        city.casefold() in title_lower
        and not any(place in context_lower for place in other_japanese_cities if place != city.casefold())
        and not any(place in title_lower for place in other_japanese_cities if place != city.casefold())
    ):
        return True
    if activities and any(activity.name.casefold() in title.casefold() for activity in activities.activities[:8]):
        return True
    return False


def _currency_for(match: re.Match[str], context: str, trip: TripRequest) -> tuple[str | None, list[str]]:
    before = (match.group("before") or "").strip()
    range_currency = (match.group("range_currency") or "").strip()
    after = (match.group("after") or "").strip()
    tokens = [token.upper() for token in (before, range_currency, after) if token]
    explicit_codes = [token for token in tokens if token in ISO_4217_CURRENCY_CODES]
    if len(set(explicit_codes)) > 1:
        return None, ["ambiguous_currency"]
    currency = explicit_codes[0] if explicit_codes else None
    lowered_tokens = [token.casefold() for token in (before, range_currency, after)]
    if not currency and any(token in {"yen", "japanese yen"} for token in lowered_tokens):
        currency = "JPY"
    symbols = {token for token in (before, range_currency, after) if token in {"$", "\u00a3", "\u20ac", "\u00a5", "\u20b9"}}
    if not currency and symbols:
        if symbols == {"\u20b9"}:
            currency = "INR"
        elif symbols == {"\u00a5"} and re.search(r"\b(?:japan|japanese|kyoto)\b", f"{trip.destination} {context}", re.I):
            currency = "JPY"
        else:
            return None, ["ambiguous_currency"]
    if not currency:
        return None, ["missing_currency"]
    if currency not in SUPPORTED_COST_CURRENCIES:
        return None, ["unsupported_currency"]
    return currency, []


def _basis(
    context: str,
    category: CostResearchCategory,
    amount_position: int | None = None,
) -> tuple[str | None, str | None, str | None, list[str]]:
    total_marker = re.search(r"\b(?:total(?:s|ed|ing)?|full stay|full experience)\b", context, re.I)
    if total_marker and amount_position is not None and total_marker.end() < amount_position:
        context = context[total_marker.end():]
    normalized = re.sub(r"\s+", " ", context).strip()
    fare_classes = list(re.finditer(r"\b(adult|child)(?:s|ren)?\b", normalized, re.I))
    fare_class = None
    if fare_classes:
        fare_class = min(fare_classes, key=lambda item: abs(item.start() - len(normalized) // 2)).group(1).casefold()

    ticket_type = None
    if re.search(r"\b(?:two|2|three|3)[- ]day pass\b|\b(?:48|72)[- ]hour pass\b", normalized, re.I):
        ticket_type = "multi_day_pass"
    elif re.search(r"\b(?:one[- ]day|1[- ]day|day)(?:\s+(?:adult|child))?\s+pass\b|\bvalid for one day\b", normalized, re.I):
        ticket_type = "day_pass"
    elif re.search(r"\bsame[- ]day ticket\b|\bsingle[- ]ride ticket\b|\bsingle ticket\b", normalized, re.I):
        ticket_type = "single_ticket"
    elif re.search(r"\bone\s+ticket\b", normalized, re.I):
        ticket_type = "single_ticket"

    if category == "local_transportation" and ticket_type == "multi_day_pass":
        return "per_person", fare_class, ticket_type, []
    if category == "local_transportation" and ticket_type == "day_pass":
        fare_class = fare_class or ("adult" if re.search(r"\badult", normalized, re.I) else None)
        return "per_person_per_day", fare_class, ticket_type, []

    # Kyoto transit fares are commonly stated as "yen per adult/child" with
    # the pass or fare noun nearby. Keep those as fare units, not generic
    # per-person travel costs.
    if category == "local_transportation" and ticket_type != "day_pass" and re.search(
        r"\b(?:fare|bus|subway|transit|single ticket|flat fare|ride)\b", normalized, re.I
    ):
        fare_basis = re.search(r"\bper\s+(?:adult|child)\b", normalized, re.I)
        if fare_basis:
            return "per_ride", fare_class, ticket_type or "single_ticket", []

    matches = [(basis, pattern.search(normalized)) for basis, pattern in _BASIS_RULES]
    found = [(basis, match) for basis, match in matches if match]
    if not found:
        if category == "activities_attractions" and re.search(
            r"(?:\b(?:entry|entrance|admission)\s+fee\b|\b(?:entry|entrance|admission)\s+(?:is|costs?|:)|\bper\s+admission\b)",
            normalized,
            re.I,
        ):
            return "per_admission", fare_class, ticket_type, []
        if category == "local_transportation" and fare_class and re.search(r"fare|bus|subway|transit|ticket", normalized, re.I):
            return "per_ride", fare_class, ticket_type, []
        if ticket_type == "day_pass":
            return "per_day", fare_class, ticket_type, []
        return None, fare_class, ticket_type, ["missing_cost_basis"]

    # A compound basis also matches its shorter suffix (for example,
    # "per person per night" contains "per night"). Ignore contained matches.
    selected_basis, selected_match = max(found, key=lambda item: len(item[1].group(0)))
    incompatible = [
        (basis, match) for basis, match in found
        if not (match.start() >= selected_match.start() and match.end() <= selected_match.end())
    ]
    if incompatible:
        return None, fare_class, ticket_type, ["ambiguous_cost_basis"]
    if category == "accommodation":
        if selected_basis == "per_person_per_night":
            pass
        elif selected_basis == "per_night" and re.search(r"\b(?:room|hotel room|guest room)\b", normalized, re.I):
            selected_basis = "per_room_per_night"
        elif selected_basis == "per_night" and re.search(r"\bcapsule\b", normalized, re.I):
            selected_basis = "per_capsule_per_night"
        elif selected_basis == "per_person" and re.search(r"\bper\s+(?:person|travell?er)\s+per\s+night\b", normalized, re.I):
            selected_basis = "per_person_per_night"
        elif selected_basis not in {"per_room_per_night", "per_capsule_per_night", "per_person_per_room_per_night"}:
            return None, fare_class, ticket_type, ["ambiguous_accommodation_unit"]
    return selected_basis, fare_class, ticket_type, []


def _normalized_entity_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _activity_entity_name(
    title: str,
    context: str,
    activities: ActivityIntelligence | None,
) -> str | None:
    # Search-result titles can contain an entire copied post with many prices.
    # Only a unique attraction name in the local price statement may attribute it.
    del title
    evidence = f" {_normalized_entity_text(context)} "
    if not activities:
        return None
    matches = {
        activity.name
        for activity in activities.activities
        if (normalized := _normalized_entity_text(activity.name))
        and f" {normalized} " in evidence
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _line_units(text: str) -> list[str]:
    pieces: list[str] = []
    separators = (
        r"[\r\n;|•]+|"
        r"\s+and\s+(?=(?:accommodation|food|flight|airfare|transport|transit|entry fee|admission|bus fare|hotel|meal)\b)|"
        r"(?<=[.!?])\s+(?=[A-Z0-9])|\U0001F4CD\s*(?=\\?\s*\d+\s*[.)])"
    )
    for block in re.split(separators, text, flags=re.I):
        block = re.sub(r"\\([.()])", r"\1", block)
        block = re.sub(r"<[^>]+>", " ", block).strip()
        if block:
            pieces.append(block)
    return pieces


def _verified_free_admissions(
    source: CostResearchSource,
    activities: ActivityIntelligence | None,
) -> list[VerifiedFreeAdmissionEvidence]:
    if source.source_type != "official" or not activities:
        return []
    explicit_free = re.compile(
        r"\b(?:free\s+(?:admission|entry|entrance)|"
        r"(?:admission|entry|entrance)\s+(?:is|are)\s+free|"
        r"no\s+(?:admission|entry|entrance)\s+fee)\b",
        re.I,
    )
    results: list[VerifiedFreeAdmissionEvidence] = []
    seen: set[tuple[str, str]] = set()
    for text in (source.snippet, source.page_text_excerpt):
        for unit in _line_units(text):
            if not explicit_free.search(unit):
                continue
            activity_name = _activity_entity_name(source.title, unit, activities)
            if not activity_name:
                continue
            quote = re.sub(r"\s+", " ", unit).strip()[:500]
            key = activity_name, quote.casefold()
            if key in seen:
                continue
            seen.add(key)
            results.append(VerifiedFreeAdmissionEvidence(
                activity_name=activity_name,
                source_url=source.url,
                evidence_quote=quote,
                retrieved_on=source.retrieved_on,
            ))
    return results


def _statements_in_text(
    text: str,
    *,
    category: CostResearchCategory,
    trip: TripRequest,
    relevant: bool,
    title: str,
    activities: ActivityIntelligence | None,
) -> list[CostPriceStatement]:
    statements: list[CostPriceStatement] = []
    for line in _line_units(text):
        matches = [
            match for match in _PRICE_RE.finditer(line)
            if _has_explicit_currency_token(match)
        ]
        recognized_spans: set[tuple[int, int]] = set()
        for index, match in enumerate(matches):
            previous_end = matches[index - 1].end() if index else max(0, match.start() - 100)
            next_start = matches[index + 1].start() if index + 1 < len(matches) else min(len(line), match.end() + 100)
            left = max(previous_end, match.start() - 100)
            right = min(next_start, match.end() + 100)
            context = line[left:right]
            quote = re.sub(r"\s+", " ", context).strip()
            currency, currency_reasons = _currency_for(match, context, trip)
            basis_context = context
            if category == "local_transportation" and re.search(
                r"\b(?:one|1)[- ]day pass\b|\b(?:two|2|three|3)[- ]day pass\b",
                title,
                re.I,
            ):
                basis_context = f"{title}. {context}"
            pass_duration_match = re.search(
                r"\b(two|2|three|3)[- ]day pass\b|\b(48|72)[- ]hour pass\b",
                basis_context,
                re.I,
            ) if category == "local_transportation" else None
            pass_duration_days = None
            if pass_duration_match:
                token = next(value for value in pass_duration_match.groups() if value)
                pass_duration_days = {"two": 2, "2": 2, "three": 3, "3": 3, "48": 2, "72": 3}[token.casefold()]
            basis, fare_class, ticket_type, basis_reasons = _basis(basis_context, category, match.start() - left)
            low = float(match.group("low").replace(",", ""))
            high = float((match.group("high") or match.group("low")).replace(",", ""))
            reasons = list(currency_reasons) + list(basis_reasons)
            if low > high:
                reasons.append("ambiguous_price")
            match_position = match.start() - left
            aggregate = _AGGREGATE_PRICE.search(context)
            if aggregate and aggregate.start() < match_position:
                reasons.append("ambiguous_cost_basis")
            if _GENERIC_TRIP_TOTAL.search(context):
                reasons.append("irrelevant_source")
            if _ILLUSTRATIVE_CONTEXT.search(context):
                reasons.append("illustrative_example")
            if category == "accommodation" and _TAX_AMOUNT_CONTEXT.search(context[:match_position]):
                reasons.append("tax_amount")
            statement_context = f"{title} {context}"
            statement_relevant = (
                relevant
                and _statement_destination_mentioned(title, context, trip, activities)
                and _has_category_context(statement_context, category)
            )
            if category == "transportation":
                origin_city = trip.origin.split(",", 1)[0].strip().casefold()
                statement_relevant = statement_relevant and origin_city in context.casefold()
            if not statement_relevant:
                reasons.append("irrelevant_source")
            entity_name = (
                _activity_entity_name(title, context, activities)
                if category == "activities_attractions" else None
            )
            taxes_included = None
            if re.search(r"(?:tax(?:es)?\s+included|inclusive\s+of\s+tax)", context, re.I):
                taxes_included = True
            elif re.search(r"(?:tax(?:es)?\s+(?:excluded|extra|not included)|excluding\s+tax)", context, re.I):
                taxes_included = False
            description = quote[:240]
            statements.append(CostPriceStatement(
                category=category,
                scope="entity" if entity_name else "category",
                entity_name=entity_name,
                description=description,
                amount_min=low,
                amount_max=high,
                currency=currency,
                basis=basis,
                fare_class=fare_class,
                ticket_type=ticket_type,
                pass_duration_days=pass_duration_days,
                taxes_included=taxes_included,
                confidence_level="low" if not reasons else None,
                evidence_quote=quote[:500],
                accepted=not reasons,
                rejection_reasons=list(dict.fromkeys(reasons)),
            ))
            recognized_spans.add((match.start(), match.end()))

        # Report a plausible labeled amount with no currency as a rejected statement,
        # while excluding years, durations, dates and unrelated page numerals.
        for number in _UNLABELED_NUMBER_RE.finditer(line):
            if any(start <= number.start() and number.end() <= end for start, end in recognized_spans):
                continue
            value = float(number.group("amount").replace(",", ""))
            if 1900 <= value <= 2100:
                continue
            left = max(0, number.start() - 32)
            right = min(len(line), number.end() + 32)
            context = line[left:right]
            prefix = line[max(0, number.start() - 40):number.start()]
            suffix = line[number.end():min(len(line), number.end() + 24)]
            direct_label = bool(_DIRECT_PRICE_LABEL.search(prefix)) or bool(
                re.match(r"\s*(?:per\s+(?:person|travell?er|adult|child|ride|ticket|admission)|each\s+(?:person|adult|child|ticket))\b", suffix, re.I)
            )
            if not direct_label or _NON_PRICE_UNIT.search(context):
                continue
            basis, fare_class, ticket_type, basis_reasons = _basis(context, category, number.start() - left)
            reasons = ["missing_currency", *basis_reasons]
            if _GENERIC_TRIP_TOTAL.search(context):
                reasons.append("irrelevant_source")
            statement_context = f"{title} {context}"
            statement_relevant = (
                relevant
                and _statement_destination_mentioned(title, context, trip, activities)
                and _has_category_context(statement_context, category)
            )
            if not statement_relevant:
                reasons.append("irrelevant_source")
            quote = re.sub(r"\s+", " ", context).strip()
            statements.append(CostPriceStatement(
                category=category,
                description=quote[:240],
                amount_min=value,
                amount_max=value,
                currency=None,
                basis=basis,
                fare_class=fare_class,
                ticket_type=ticket_type,
                evidence_quote=quote[:500],
                accepted=False,
                rejection_reasons=list(dict.fromkeys(reasons)),
            ))
    return statements


def _statement_key(statement: CostPriceStatement) -> tuple:
    normalized_quote = re.sub(r"\W+", " ", statement.evidence_quote.casefold()).strip()
    return (
        statement.category, statement.amount_min, statement.amount_max,
        statement.currency, statement.basis, statement.fare_class,
        statement.ticket_type, normalized_quote,
    )


def _markdown_cells(line: str) -> list[str]:
    if "|" not in line:
        return []
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _accommodation_table_statements(
    text: str,
    *,
    trip: TripRequest,
    title: str,
    url: str,
    retrieved_on: date,
) -> list[CostPriceStatement]:
    """Extract Kyoto table cells only when the nearby caption establishes a unit."""
    if not text or trip.destination.split(",", 1)[0].strip().casefold() != "kyoto":
        return []
    lines = text.splitlines()
    results: list[CostPriceStatement] = []
    for header_index, header_line in enumerate(lines):
        header = _markdown_cells(header_line)
        normalized_header = [re.sub(r"[^a-z]+", " ", cell.casefold()).strip() for cell in header]
        if not header or "kyoto" not in normalized_header:
            continue
        if not any("property type" in cell or "accommodation type" in cell for cell in normalized_header):
            continue
        kyoto_index = normalized_header.index("kyoto")
        caption_start = max(0, header_index - 6)
        caption = " ".join(lines[caption_start:header_index]).casefold()
        has_nightly_scope = bool(re.search(r"one[- ]night|per[- ]night|nightly rate|rate per night", caption))
        per_room = bool(re.search(r"per room|\d+\s+guests? per room", caption))
        per_person = bool(re.search(r"per person per night|per person,? per night", caption))
        per_capsule = bool(re.search(r"per capsule per night", caption))
        taxes_included = True if re.search(r"tax(?:es)? included|tax included", caption) else (
            False if re.search(r"tax(?:es)? excluded|excluding tax|tax extra", caption) else None
        )

        for row_index in range(header_index + 1, min(len(lines), header_index + 40)):
            cells = _markdown_cells(lines[row_index])
            if not cells:
                if row_index > header_index + 1:
                    break
                continue
            normalized_cells = [re.sub(r"\s+", " ", cell).casefold() for cell in cells]
            if any(cell == "kyoto" for cell in normalized_cells):
                continue
            if len(cells) <= kyoto_index or len(cells) < len(header):
                # Stop at another table or malformed row; do not carry a stale caption.
                if row_index > header_index + 1:
                    break
                continue
            label = re.sub(r"\s+", " ", cells[0]).strip()
            if not label or re.search(r"property type|nationwide|prefecture", label, re.I):
                continue
            cell = cells[kyoto_index]
            matches = [match for match in _PRICE_RE.finditer(cell) if any(match.group(name) for name in ("before", "range_currency", "after"))]
            if not matches:
                continue
            tax_row = bool(re.search(
                r"^\s*(?:(?:kyoto|japan(?:ese)?)\s+)?(?:(?:accommodation|lodging|hotel|city|municipal|consumption)\s+)?(?:tax|levy)\b",
                label,
                re.I,
            ))
            if tax_row:
                for tax_match in matches:
                    currency, currency_reasons = _currency_for(tax_match, f"{label} Kyoto {cell}", trip)
                    amount_min = float(tax_match.group("low").replace(",", ""))
                    amount_max = float((tax_match.group("high") or tax_match.group("low")).replace(",", ""))
                    quote = re.sub(r"\s+", " ", f"{label} | Kyoto: {cell}").strip()
                    results.append(CostPriceStatement(
                        category="accommodation",
                        scope="category",
                        source_title=title,
                        source_url=url,
                        retrieved_on=retrieved_on,
                        description=f"{label}: {cell} (tax amount, not room rate)",
                        amount_min=amount_min,
                        amount_max=amount_max,
                        currency=currency,
                        basis=None,
                        evidence_quote=quote[:500],
                        accepted=False,
                        rejection_reasons=list(dict.fromkeys(["tax_amount", *currency_reasons])),
                    ))
                continue
            # A single destination cell should contain a single quote/range.
            # Multiple prices in that cell remain ambiguous.
            match = matches[0]
            context = f"{label} Kyoto {cell} {caption}"
            currency, currency_reasons = _currency_for(match, context, trip)
            basis = None
            reasons = list(currency_reasons)
            if re.search(r"\b(?:illustrative|example|for example|tax calculation)\b", f"{caption} {cell}", re.I):
                reasons.append("illustrative_example")
            capsule_row = "capsule" in label.casefold()
            if capsule_row and has_nightly_scope and per_capsule:
                basis = "per_capsule_per_night"
            elif capsule_row and has_nightly_scope and re.search(r"capsule hotels? (?:are )?sold per person", text, re.I):
                basis = "per_person_per_night"
            elif capsule_row:
                reasons.append("ambiguous_accommodation_unit")
            elif has_nightly_scope and per_room:
                basis = "per_room_per_night"
            elif has_nightly_scope and per_person:
                basis = "per_person_per_night"
            else:
                reasons.append("ambiguous_accommodation_unit")
            if len(matches) != 1:
                reasons.append("ambiguous_price")
            if not has_nightly_scope:
                reasons.append("missing_cost_basis")
            low = float(match.group("low").replace(",", ""))
            high = float((match.group("high") or match.group("low")).replace(",", ""))
            if low > high:
                reasons.append("ambiguous_price")
            quote = re.sub(r"\s+", " ", f"{lines[caption_start:header_index][-1] if header_index > caption_start else ''} | {label} | Kyoto: {cell}").strip()
            results.append(CostPriceStatement(
                category="accommodation",
                scope="category",
                source_title=title,
                source_url=url,
                retrieved_on=retrieved_on,
                description=f"{label} in Kyoto: {cell}; {basis or 'unit unclear'}",
                amount_min=low,
                amount_max=high,
                currency=currency,
                basis=basis,
                taxes_included=taxes_included,
                confidence_level="low" if not reasons else None,
                evidence_quote=quote[:500],
                accepted=not reasons,
                rejection_reasons=list(dict.fromkeys(reasons)),
            ))
        # The first matching property-rate table is sufficient for this page;
        # later nationwide/monthly total tables have different bases.
        if results:
            break
    return results


_ESTIMATE_BASIS = {
    "per_person": "per_traveler",
    "per_person_per_day": "per_traveler_per_day",
    "per_person_per_night": "per_traveler_per_night",
    "per_room_per_night": "per_room_per_night",
    "per_capsule_per_night": "per_capsule_per_night",
    "per_person_per_room_per_night": "per_person_per_room_per_night",
    "per_person_per_day": "per_traveler_per_day",
    "per_night": "per_night",
    "per_day": "per_day",
    "per_ride": "per_ride",
    "per_admission": "per_admission",
    "per_trip": "per_trip",
}

_CATEGORY_SCALABLE_BASES: dict[CostResearchCategory, set[str]] = {
    "transportation": {"per_person", "per_person_per_day", "per_trip"},
    "accommodation": {"per_room_per_night", "per_capsule_per_night", "per_person_per_night", "per_person_per_room_per_night"},
    "food_dining": {"per_person_per_day"},
    "local_transportation": {"per_ride", "per_person_per_day"},
    "activities_attractions": {"per_person", "per_admission"},
}


def _estimate_from_statement(
    statement: CostPriceStatement,
    *,
    trip: TripRequest,
    source: CostResearchSource,
    retrieved_on: date,
    allow_class_specific: bool = False,
) -> BudgetCostEstimate | None:
    estimate_basis = _ESTIMATE_BASIS.get(statement.basis or "")
    if not statement.accepted or not estimate_basis or not statement.currency:
        return None
    if statement.basis not in _CATEGORY_SCALABLE_BASES[statement.category]:
        return None
    # Fare-class prices require an explicit confirmation with the applicable
    # adult/child count. A generic traveler count is not enough to infer age.
    if statement.fare_class and not allow_class_specific:
        return None
    if statement.category == "activities_attractions" and (statement.scope != "entity" or not statement.entity_name):
        return None
    return BudgetCostEstimate(
        category=statement.category,
        scope=statement.scope,
        entity_name=statement.entity_name,
        origin=trip.origin,
        destination=trip.destination,
        amount=statement.amount_max,
        amount_min=statement.amount_min,
        amount_max=statement.amount_max,
        currency=statement.currency,
        basis=estimate_basis,
        fare_class=statement.fare_class,
        taxes_included=statement.taxes_included,
        certainty="estimated",
        source=source.title,
        source_url=source.url,
        retrieved_on=retrieved_on,
        confidence_level="low",
        source_type=source.source_type,
        evidence_quote=statement.evidence_quote,
    )


def research_trip_costs(
    trip: TripRequest,
    activities: ActivityIntelligence | None = None,
    *,
    search: Callable[..., list[dict]] | None = None,
) -> CostResearchResult:
    """Extract distinct nearby price statements; never collapse page alternatives."""
    provider = search or search_trip_costs
    retrieved_on = date.today()
    search_errors: dict[str, str] = {}
    source_records: dict[str, CostResearchSource] = {}
    source_statements: dict[str, list[CostPriceStatement]] = {}

    for category, query in _category_queries(trip, activities):
        try:
            rows = provider(query=query, max_results=5 if category == "local_transportation" else 3)
        except Exception as error:
            search_errors[category] = type(error).__name__
            continue

        for row in rows or []:
            title = str(row.get("title", "")).strip() or "Untitled search result"
            url = str(row.get("url", "")).strip()
            if not url:
                continue
            canonical = _canonical_url(url)
            snippet = str(row.get("content", "")).strip()
            raw_content = str(row.get("raw_content", "")).strip()
            full_context = f"{title}\n{snippet}\n{raw_content}"
            relevant = _destination_mentioned(full_context, trip, activities) and _has_category_context(full_context, category)
            source = source_records.get(canonical)
            if source is None:
                source = CostResearchSource(
                    title=title,
                    url=url,
                    retrieved_on=retrieved_on,
                    excerpt=(snippet or raw_content)[:2000],
                    snippet=snippet[:1200],
                    page_text_excerpt=raw_content[:1200],
                    page_content_retrieved=bool(raw_content),
                    source_type=_source_type(url),
                    category=category,
                    relevant=relevant,
                    queries=[query],
                    categories=[category],
                )
                source_records[canonical] = source
                source_statements[canonical] = []
            else:
                if query not in source.queries:
                    source.queries.append(query)
                if category not in source.categories:
                    source.categories.append(category)
                source.relevant = source.relevant or relevant
                if snippet and not source.snippet:
                    source.snippet = snippet[:1200]
                if raw_content and not source.page_content_retrieved:
                    source.page_text_excerpt = raw_content[:1200]
                    source.page_content_retrieved = True

            extracted: list[CostPriceStatement] = []
            # Snippets are often the useful part when page extraction returns a
            # cookie wall or an unrelated page section. Parse both independently.
            for evidence_text in dict.fromkeys(item for item in (snippet, raw_content) if item):
                extracted.extend(_statements_in_text(
                    evidence_text,
                    category=category,
                    trip=trip,
                    relevant=relevant,
                    title=title,
                    activities=activities,
                ))
            if category == "accommodation":
                extracted.extend(_accommodation_table_statements(
                    raw_content or snippet,
                    trip=trip,
                    title=title,
                    url=url,
                    retrieved_on=retrieved_on,
                ))
                table_prices = {
                    (item.amount_min, item.amount_max, item.currency)
                    for item in extracted
                    if item.accepted and item.category == "accommodation"
                }
                if table_prices:
                    extracted = [
                        item for item in extracted
                        if item.accepted or (item.amount_min, item.amount_max, item.currency) not in table_prices
                    ]
            existing_keys = {_statement_key(item) for item in source_statements[canonical]}
            for statement in extracted:
                statement = statement.model_copy(update={
                    "source_title": source.title,
                    "source_url": source.url,
                    "retrieved_on": retrieved_on,
                })
                key = _statement_key(statement)
                normalized_quote = re.sub(r"\W+", " ", statement.evidence_quote.casefold()).strip()
                duplicate_index = next((index for index, prior in enumerate(source_statements[canonical]) if
                    prior.category == statement.category
                    and prior.amount_min == statement.amount_min
                    and prior.amount_max == statement.amount_max
                    and prior.currency == statement.currency
                    and prior.basis == statement.basis
                    and prior.entity_name == statement.entity_name
                    and prior.fare_class == statement.fare_class
                    and prior.ticket_type == statement.ticket_type
                    and prior.pass_duration_days == statement.pass_duration_days
                    and prior.taxes_included == statement.taxes_included
                    and (
                        re.sub(r"\W+", " ", prior.evidence_quote.casefold()).strip() in normalized_quote
                        or normalized_quote in re.sub(r"\W+", " ", prior.evidence_quote.casefold()).strip()
                    )
                ), None)
                if duplicate_index is not None:
                    prior = source_statements[canonical][duplicate_index]
                    if any(reason in statement.rejection_reasons for reason in ("ambiguous_accommodation_unit", "tax_amount")):
                        prior.rejection_reasons = list(dict.fromkeys(
                            prior.rejection_reasons + [
                                reason for reason in statement.rejection_reasons
                                if reason in {"ambiguous_accommodation_unit", "tax_amount"}
                            ]
                        ))
                    if statement.accepted and not prior.accepted:
                        source_statements[canonical][duplicate_index] = statement
                elif key not in existing_keys:
                    source_statements[canonical].append(statement)
                    existing_keys.add(key)

    sources: list[CostResearchSource] = []
    statements: list[CostPriceStatement] = []
    estimates_by_category: dict[CostResearchCategory, list[BudgetCostEstimate]] = {}
    for canonical, source in source_records.items():
        source.price_statements = source_statements[canonical]
        source.rejection_reasons = list(dict.fromkeys(
            reason
            for item in source.price_statements
            for reason in item.rejection_reasons
        ))
        if not source.price_statements:
            source.rejection_reasons = ["irrelevant_source"] if not source.relevant else ["missing_amount"]
        sources.append(source)
        statements.extend(source.price_statements)
        for statement in source.price_statements:
            estimate = _estimate_from_statement(statement, trip=trip, source=source, retrieved_on=retrieved_on)
            if estimate:
                estimates_by_category.setdefault(statement.category, []).append(estimate)

    options: list[CostEvidenceOption] = []
    for source in sources:
        for statement in source.price_statements:
            option_estimate = _estimate_from_statement(
                statement,
                trip=trip,
                source=source,
                retrieved_on=retrieved_on,
                allow_class_specific=True,
            )
            if option_estimate is None or statement.category == "activities_attractions":
                continue
            option_seed = "|".join((
                statement.category,
                source.url,
                statement.basis or "",
                statement.ticket_type or "",
                statement.fare_class or "",
                str(statement.amount_min),
                str(statement.amount_max),
                re.sub(r"\W+", " ", statement.evidence_quote.casefold()).strip(),
            ))
            option_id = sha256(option_seed.encode("utf-8")).hexdigest()[:20]
            group_seed = "|".join((
                statement.category,
                source.url,
                statement.basis or "",
                statement.ticket_type or "",
                re.sub(
                    r"\b(?:adult|child)\b|\b\d[\d,]*(?:\.\d+)?\b|¥|JPY|yen",
                    " ",
                    statement.description.casefold(),
                ),
            ))
            group_id = sha256(group_seed.encode("utf-8")).hexdigest()[:16]
            options.append(CostEvidenceOption(
                option_id=option_id,
                group_id=group_id,
                label=statement.description[:120],
                estimate=option_estimate,
            ))

    estimates: list[BudgetCostEstimate] = []
    for category, category_estimates in estimates_by_category.items():
        if category == "activities_attractions":
            estimates.extend(category_estimates)
        elif len(category_estimates) == 1:
            estimates.extend(category_estimates)
        # Multiple category prices are preserved as individual statements but
        # not summed as if they were separate trip expenses or silently chosen.

    verified_free = [
        evidence
        for source in sources
        if "activities_attractions" in source.categories
        for evidence in _verified_free_admissions(source, activities)
    ]

    if estimates or verified_free or any(statement.accepted for statement in statements):
        status = "available" if not search_errors else "partial"
        note = "Source-based indicative price statements; alternatives remain separate and no booking prices were confirmed. Foreign currencies remain unconverted."
    elif sources or (search_errors and len(search_errors) < len(_category_queries(trip, activities))):
        status = "partial"
        note = "Sources were searched, but no individually interpretable price statements were available for allocation. Rejected statements include their reasons."
    else:
        status = "unavailable"
        note = "No cost research sources were returned; unsupported costs remain unallocated."
    return CostResearchResult(
        status=status,
        sources=sources,
        estimates=estimates,
        options=options,
        verified_free_activities=verified_free,
        price_statements=statements,
        search_errors=search_errors,
        note=note,
    )


def resolve_cost_option_selections(
    options: list[CostEvidenceOption],
    selections: list[dict],
    trip: TripRequest,
) -> list[BudgetCostEstimate]:
    """Validate explicit evidence choices and apply only user-specified quantities."""
    available = {option.option_id: option for option in options}
    selected_estimates: list[BudgetCostEstimate] = []
    selected_categories: dict[str, set[str]] = {}
    classes_by_group: dict[str, set[str]] = {}
    travelers_by_group: dict[str, int] = {}
    used_ids: set[str] = set()
    for selection in selections:
        if not isinstance(selection, dict):
            raise ValueError("Each cost option selection must be an object.")
        option_id = selection.get("option_id")
        if not isinstance(option_id, str) or option_id in used_ids:
            raise ValueError("A cost option cannot be selected more than once.")
        used_ids.add(option_id)
        option = available.get(option_id)
        if option is None:
            raise ValueError("A selected cost option is not available for this trip.")
        estimate = option.estimate
        if estimate.currency.upper() != trip.currency.upper():
            raise ValueError("Selected cost option currency differs from the trip budget; no conversion is available.")
        selected_categories.setdefault(estimate.category, set()).add(option.group_id)
        traveler_count = selection.get("traveler_count")
        if estimate.fare_class:
            if isinstance(traveler_count, bool) or not isinstance(traveler_count, int) or not 1 <= traveler_count <= trip.travelers:
                raise ValueError(f"Confirm the number of {estimate.fare_class} travellers for this option.")
            estimate = estimate.model_copy(update={"traveler_count_override": traveler_count})
            fare_classes = classes_by_group.setdefault(option.group_id, set())
            if estimate.fare_class in fare_classes:
                raise ValueError("Select at most one price option per traveller fare class in a pass group.")
            fare_classes.add(estimate.fare_class)
            travelers_by_group[option.group_id] = travelers_by_group.get(option.group_id, 0) + traveler_count
        elif traveler_count is not None:
            raise ValueError("Traveller counts can only be supplied for adult- or child-specific fares.")
        quantity = selection.get("quantity")
        if estimate.basis == "per_ride":
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                raise ValueError("Enter the total ride count before selecting a per-ride fare.")
            estimate = estimate.model_copy(update={"quantity_override": quantity})
        elif quantity is not None:
            raise ValueError("A quantity is only accepted for a per-ride fare.")
        selected_estimates.append(estimate)
    if any(len(groups) > 1 for groups in selected_categories.values()):
        raise ValueError("Choose one competing cost option group per category.")
    if any(count > trip.travelers for count in travelers_by_group.values()):
        raise ValueError("Adult and child counts for a selected option cannot exceed the trip traveller count.")
    return selected_estimates
