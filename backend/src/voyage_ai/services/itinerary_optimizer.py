from ortools.constraint_solver import (
    pywrapcp,
    routing_enums_pb2,
)

from voyage_ai.models.activity import (
    ActivityIntelligence,
)
from voyage_ai.models.itinerary import (
    OptimizedDay,
    OptimizedItinerary,
    ScheduledActivity,
)
from voyage_ai.models.routing import (
    TravelMatrix,
)


def _admission_status(activity, budget_currency: str | None) -> str:
    if (
        activity.admission_status == "verified_free"
        and activity.cost_source_type == "official"
        and activity.cost_source_url
        and activity.cost_evidence
    ):
        return "verified_free"
    if (
        activity.estimated_cost is not None
        and activity.estimated_cost > 0
        and activity.currency
        and (budget_currency is None or activity.currency.upper() == budget_currency.upper())
    ):
        return "priced"
    return "unpriced"


def _build_augmented_time_matrix(
    travel_matrix: TravelMatrix,
) -> list[list[int]]:
    """
    Add a dummy start/end location.

    Node 0 = virtual hotel/depot.

    For this first optimizer version,
    travel from/to the virtual depot is zero.

    Later, the real hotel will replace this.
    """

    original = (
        travel_matrix.durations_minutes
    )

    size = len(original)

    augmented_size = size + 1

    matrix = [
        [0 for _ in range(augmented_size)]
        for _ in range(augmented_size)
    ]


    for i in range(size):

        for j in range(size):

            value = original[i][j]

            if value is None:
                raise ValueError(
                    "Travel matrix contains "
                    "an unresolved travel time."
                )

            matrix[i + 1][j + 1] = int(
                round(value)
            )


    return matrix


def _activity_drop_penalty(activity) -> int:
    """Value a stop in the same minute units as travel/service costs.

    A stop is worth its modeled visit time plus a bounded preference and
    confidence bonus. This lets the solver omit a low-priority distant stop
    when its road travel overhead is disproportionate.
    """
    return (
        activity.estimated_duration_minutes
        + round(activity.preference_score * 90)
        + round(activity.confidence * 30)
    )

def calculate_weather_penalty(
    environment: str,
    weather_sensitive: bool,
    suitability: str | None,
) -> int:
    """
    Return an optimization penalty for placing
    a weather-sensitive activity on a poor day.

    These are VoyageAI planning heuristics,
    not official weather warning scores.
    """

    if not weather_sensitive:
        return 0

    if suitability is None:
        return 0

    suitability = suitability.lower()

    if suitability == "good":
        return 0

    if suitability == "caution":

        if environment == "outdoor":
            return 1200

        if environment == "mixed":
            return 500

        return 0

    if suitability == "poor":

        if environment == "outdoor":
            return 5000

        if environment == "mixed":
            return 2000

        return 0

    if suitability == "unknown":
        return 200

    return 0


def optimize_itinerary(
    activity_intelligence: ActivityIntelligence,
    travel_matrix: TravelMatrix,
    number_of_days: int,
    daily_minutes: int = 600,
    activity_budget: float | None = None,
    weather_suitability_by_day: list[str] | None = None,
    budget_currency: str | None = None,
    travelers: int = 1,
    daily_minutes_by_day: list[int] | None = None,
    day_schedule_notes: list[str | None] | None = None,
    daily_buffer_minutes_by_day: list[int] | None = None,
) -> OptimizedItinerary:
    """
    Optimize activity selection, day assignment,
    and ordering using Google OR-Tools.

    Current constraints:

    - Each activity is visited at most once.
    - Every day has a maximum time budget.
    - Activity duration counts toward day time.
    - Travel time counts toward day time.
    - Higher preference activities receive
      a higher penalty if dropped.

    When an approved activity budget is present, sourced costs are a hard
    constraint and activities with missing or mismatched-currency costs are
    excluded rather than treated as free.
    """

    if number_of_days < 1:
        raise ValueError(
            "number_of_days must be at least 1."
        )
    if travelers < 1:
        raise ValueError("travelers must be at least 1.")

    if daily_minutes_by_day is None:
        daily_minutes_by_day = [daily_minutes] * number_of_days
    if len(daily_minutes_by_day) != number_of_days or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in daily_minutes_by_day
    ):
        raise ValueError("daily_minutes_by_day must contain a non-negative integer capacity for every day.")
    if day_schedule_notes is None:
        day_schedule_notes = [None] * number_of_days
    if len(day_schedule_notes) != number_of_days:
        raise ValueError("day_schedule_notes must contain one note for every day.")
    if daily_buffer_minutes_by_day is None:
        daily_buffer_minutes_by_day = [0] * number_of_days
    if len(daily_buffer_minutes_by_day) != number_of_days or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in daily_buffer_minutes_by_day
    ):
        raise ValueError("daily_buffer_minutes_by_day must contain a non-negative integer for every day.")

    if (
        activity_budget is not None
        and activity_budget < 0
    ):
        raise ValueError(
            "activity_budget cannot be negative."
        )


    if (
        weather_suitability_by_day
        is not None
        and len(
            weather_suitability_by_day
        ) < number_of_days
    ):
        raise ValueError(
            "weather_suitability_by_day must "
            "contain at least one value "
            "for every itinerary day."
        )


    activity_by_name = {
        activity.name: activity
        for activity
        in activity_intelligence.activities
    }


    activities = []

    for location_name in travel_matrix.locations:

        activity = activity_by_name.get(
            location_name
        )

        if activity is None:
            raise ValueError(
                f"No ActivityCandidate found "
                f"for {location_name}."
            )

        if (
            activity.estimated_duration_minutes
            is None
        ):
            raise ValueError(
                f"{activity.name} does not have "
                "an estimated duration yet."
            )

        activities.append(
            activity
        )


    if not activities:
        raise ValueError(
            "No activities available "
            "for optimization."
        )

    unpriced_activities = [
        activity.name
        for activity in activities
        if _admission_status(activity, budget_currency) == "unpriced"
    ]


    travel_times = (
        _build_augmented_time_matrix(
            travel_matrix
        )
    )


    # ----------------------------------------------
    # SERVICE DURATION
    #
    # Node 0 is our virtual depot.
    # ----------------------------------------------

    service_minutes = [0]

    for activity in activities:

        service_minutes.append(
            activity.estimated_duration_minutes
        )


    node_count = len(activities) + 1

    depot = 0


    # Each "vehicle" represents one travel day.
    manager = pywrapcp.RoutingIndexManager(
        node_count,
        number_of_days,
        depot,
    )


    routing = pywrapcp.RoutingModel(
        manager
    )


    # ----------------------------------------------
    # TIME CALLBACK
    #
    # activity duration
    #       +
    # travel time to next activity
    # ----------------------------------------------

    def time_callback(
        from_index: int,
        to_index: int,
    ) -> int:

        from_node = (
            manager.IndexToNode(
                from_index
            )
        )

        to_node = (
            manager.IndexToNode(
                to_index
            )
        )


        travel = travel_times[
            from_node
        ][
            to_node
        ]


        service = service_minutes[
            from_node
        ]


        return (
            travel
            + service
        )


    transit_callback_index = (
        routing.RegisterTransitCallback(
            time_callback
        )
    )

    


    # ----------------------------------------------
    # DAILY TIME CONSTRAINT
    # ----------------------------------------------

    routing.AddDimensionWithVehicleCapacity(
        transit_callback_index,

        0,

        daily_minutes_by_day,

        True,

        "Time",
    )

    # ----------------------------------------------
    # WEATHER-AWARE OBJECTIVE
    # ----------------------------------------------

    for vehicle_id in range(
        number_of_days
    ):

        def make_cost_callback(
            current_vehicle_id: int,
        ):

            def cost_callback(
                from_index: int,
                to_index: int,
            ) -> int:

                from_node = (
                    manager.IndexToNode(
                        from_index
                    )
                )

                to_node = (
                    manager.IndexToNode(
                        to_index
                    )
                )


                travel = travel_times[
                    from_node
                ][
                    to_node
                ]


                service = service_minutes[
                    from_node
                ]


                weather_penalty = 0


                if (
                    to_node != depot
                    and
                    weather_suitability_by_day
                    is not None
                ):

                    activity = activities[
                        to_node - 1
                    ]

                    suitability = (
                        weather_suitability_by_day[
                            current_vehicle_id
                        ]
                    )


                    weather_penalty = (
                        calculate_weather_penalty(
                            environment=(
                                activity.environment
                            ),

                            weather_sensitive=(
                                activity.weather_sensitive
                            ),

                            suitability=(
                                suitability
                            ),
                        )
                    )


                return (
                    travel
                    + service
                    + weather_penalty
                )


            return cost_callback


        callback_index = (
            routing.RegisterTransitCallback(
                make_cost_callback(
                    vehicle_id
                )
            )
        )


        routing.SetArcCostEvaluatorOfVehicle(
            callback_index,
            vehicle_id,
        )



        # ----------------------------------------------
    # GLOBAL ACTIVITY BUDGET
    #
    # Only selected activities count toward
    # the budget.
    # ----------------------------------------------

    if activity_budget is not None:

        money_scale = 100

        maximum_budget = int(
            round(
                activity_budget
                * money_scale
            )
        )

        solver = routing.solver()

        budget_terms = []


        for node in range(
            1,
            node_count,
        ):

            activity = activities[
                node - 1
            ]

            node_index = manager.NodeToIndex(node)
            active = routing.ActiveVar(node_index)

            status = _admission_status(activity, budget_currency)
            if status == "unpriced":
                # Keep unknown-cost stops as provisional suggestions. They are
                # not included in priced totals or the hard known-cost cap.
                continue
            if status == "verified_free":
                continue

            activity_cost = activity.estimated_cost * (
                travelers if activity.cost_basis == "per_traveler" else 1
            )

            scaled_cost = int(
                round(
                    activity_cost
                    * money_scale
                )
            )

            budget_terms.append(
                active * scaled_cost
            )

    # When there are enough feasible stops, require one stop on every day.
    # This prevents the solver from clustering all visits on one arbitrary day.
    eligible_nodes = []
    for node, activity in enumerate(activities, start=1):
        if activity.estimated_duration_minutes > daily_minutes:
            continue
        status = _admission_status(activity, budget_currency)
        if status == "unpriced" or status == "verified_free":
            eligible_nodes.append(node)
        elif activity_budget is None or activity.estimated_cost * (
            travelers if activity.cost_basis == "per_traveler" else 1
        ) <= activity_budget + 0.01:
            eligible_nodes.append(node)
    available_vehicles = [
        vehicle_id
        for vehicle_id, capacity in enumerate(daily_minutes_by_day)
        if capacity > 0
    ]
    if available_vehicles and len(eligible_nodes) >= len(available_vehicles):
        solver = routing.solver()
        for vehicle_id in available_vehicles:
            assigned = [
                solver.IsEqualCstVar(routing.VehicleVar(manager.NodeToIndex(node)), vehicle_id)
                for node in eligible_nodes
            ]
            solver.Add(solver.Sum(assigned) >= 1)


    if activity_budget is not None and budget_terms:
        solver = routing.solver()
        solver.Add(sum(budget_terms) <= maximum_budget)


    # ----------------------------------------------
    # OPTIONAL ACTIVITIES
    #
    # OR-Tools may drop an activity if necessary.
    #
    # High-preference activities have a higher
    # dropping penalty, so the solver tries harder
    # to keep them.
    # ----------------------------------------------

    for node in range(
        1,
        node_count,
    ):

        activity = activities[
            node - 1
        ]


        penalty = _activity_drop_penalty(activity)


        routing.AddDisjunction(
            [
                manager.NodeToIndex(
                    node
                )
            ],
            penalty,
        )


    # ----------------------------------------------
    # SEARCH SETTINGS
    # ----------------------------------------------

    search_parameters = (
        pywrapcp.DefaultRoutingSearchParameters()
    )


    search_parameters.first_solution_strategy = (
        routing_enums_pb2
        .FirstSolutionStrategy
        .PATH_CHEAPEST_ARC
    )


    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2
        .LocalSearchMetaheuristic
        .GUIDED_LOCAL_SEARCH
    )


    search_parameters.time_limit.seconds = 10


    # ----------------------------------------------
    # SOLVE
    # ----------------------------------------------

    solution = routing.SolveWithParameters(
        search_parameters
    )


    if solution is None:

        raise RuntimeError(
            "OR-Tools could not find "
            "a feasible itinerary."
        )


    # ----------------------------------------------
    # EXTRACT SELECTED ROUTES
    # ----------------------------------------------

    optimized_days = []

    selected_names = []
    priced_names: list[str] = []
    verified_free_names: list[str] = []
    provisional_names: list[str] = []


    for vehicle_id in range(
        number_of_days
    ):

        index = routing.Start(
            vehicle_id
        )

        day_activities = []

        total_activity_minutes = 0
        total_travel_minutes = 0.0
        total_activity_cost = 0.0

        previous_node = 0

        sequence = 1


        while not routing.IsEnd(
            index
        ):

            node = manager.IndexToNode(
                index
            )


            if node != depot:

                activity = activities[
                    node - 1
                ]


                travel_from_previous = (
                    travel_times[
                        previous_node
                    ][
                        node
                    ]
                )


                scheduled = ScheduledActivity(
                    name=activity.name,

                    day_number=(
                        vehicle_id + 1
                    ),

                    sequence=sequence,

                    estimated_duration_minutes=(
                        activity
                        .estimated_duration_minutes
                    ),
                    duration_estimate_basis=activity.duration_estimate_basis,

                    travel_from_previous_minutes=(
                        float(
                            travel_from_previous
                        )
                    ),

                    preference_score=(
                        activity.preference_score
                    ),

                    environment=(
                        activity.environment
                    ),
                    estimated_cost=(
                        round(activity.estimated_cost * (travelers if activity.cost_basis == "per_traveler" else 1), 2)
                        if _admission_status(activity, budget_currency) == "priced" else None
                    ),
                    currency=activity.currency,
                    cost_status=activity.cost_status,
                    cost_source_url=activity.cost_source_url,
                    cost_source_type=activity.cost_source_type,
                    admission_status=_admission_status(activity, budget_currency),
                    requires_price_verification=_admission_status(activity, budget_currency) == "unpriced",
                    opening_hours_verified=activity.opening_hours_verified,
                )


                day_activities.append(
                    scheduled
                )


                selected_names.append(
                    activity.name
                )
                status = _admission_status(activity, budget_currency)
                if status == "unpriced":
                    provisional_names.append(activity.name)
                elif status == "verified_free":
                    verified_free_names.append(activity.name)
                else:
                    priced_names.append(activity.name)


                total_activity_minutes += (
                    activity
                    .estimated_duration_minutes
                )

                total_activity_cost += (
                    activity.estimated_cost * (travelers if activity.cost_basis == "per_traveler" else 1)
                    if status == "priced"
                    else 0
              )


                total_travel_minutes += (
                    travel_from_previous
                )


                previous_node = node

                sequence += 1


            index = solution.Value(
                routing.NextVar(
                    index
                )
            )


        optimized_days.append(
            OptimizedDay(
                day_number=(
                    vehicle_id + 1
                ),

                weather_suitability=(
                    weather_suitability_by_day[
                        vehicle_id
                    ]
                    if weather_suitability_by_day
                    is not None
                    else None
                ),

                schedule_note=day_schedule_notes[vehicle_id],
                buffer_minutes=daily_buffer_minutes_by_day[vehicle_id],

                activities=(
                    day_activities
                ),

                total_activity_minutes=(
                    total_activity_minutes
                ),

                total_travel_minutes=(
                    round(
                        total_travel_minutes,
                        1,
                    )
                ),

                total_activity_cost=(
                    round(
                        total_activity_cost,
                        2,
                    )
                ),
            )
        ),



    all_names = [
        activity.name
        for activity in activities
    ]


    selected_set = set(
        selected_names
    )


    dropped_names = [
        name
        for name in all_names
        if name not in selected_set
    ]

    total_selected_cost = sum(
    (
        activity.estimated_cost * (travelers if activity.cost_basis == "per_traveler" else 1)
        if _admission_status(activity, budget_currency) == "priced"
        else 0
    )
    for activity in activities
    if activity.name in selected_set
    )


    planning_limitations = []
    if provisional_names:
        planning_limitations.append(
            "Some scheduled suggestions have unknown admission prices. They are excluded from priced totals; total activity spending cannot be verified against the cap."
        )
    if any(not activity.opening_hours_verified for activity in activities if activity.name in selected_names):
        planning_limitations.append("Verified opening hours were unavailable; check hours before visiting.")
    if selected_names:
        planning_limitations.append(
            "Visit durations are planning estimates, not verified attraction durations. Daily visit and inter-stop driving capacity reserves a one-hour flexibility buffer on sightseeing days. Meals, queues, parking, and lodging/airport transfers are not modeled."
        )

    return OptimizedItinerary(
        destination=(
            activity_intelligence.destination
        ),

        days=optimized_days,

        selected_activities=(
            selected_names
        ),

        dropped_activities=(
            dropped_names
        ),

        unpriced_activities=unpriced_activities,
        priced_activities=priced_names,
        verified_free_activities=verified_free_names,
        provisional_activities=provisional_names,
        budget_status=(
            "provisional" if provisional_names
            else "within_cap" if activity_budget is not None
            else "not_budgeted"
        ),
        planning_limitations=planning_limitations,

        total_activity_cost=round(
            total_selected_cost,
            2,
        ),
        priced_activity_cost=round(total_selected_cost, 2),
        provisional_activity_cost=None if provisional_names else 0.0,

        activity_budget=(
            activity_budget
        ),

        objective_value=float(
            solution.ObjectiveValue()
        ),
    )
