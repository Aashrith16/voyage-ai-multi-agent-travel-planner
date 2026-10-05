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

    Budget and weather constraints are added
    in the next optimizer stage.
    """

    if number_of_days < 1:
        raise ValueError(
            "number_of_days must be at least 1."
        )

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

    routing.AddDimension(
        transit_callback_index,

        0,

        daily_minutes,

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

            activity_cost = (
                activity.estimated_cost
                if activity.estimated_cost
                is not None
                else 0
            )

            scaled_cost = int(
                round(
                    activity_cost
                    * money_scale
                )
            )

            node_index = (
                manager.NodeToIndex(
                    node
                )
            )


            budget_terms.append(
                routing.ActiveVar(
                    node_index
                )
                * scaled_cost
            )


        solver.Add(
            sum(budget_terms)
            <= maximum_budget
        )


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


        preference_component = int(
            activity.preference_score
            * 10000
        )


        confidence_component = int(
            activity.confidence
            * 2000
        )


        penalty = (
            5000
            + preference_component
            + confidence_component
        )


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
                )


                day_activities.append(
                    scheduled
                )


                selected_names.append(
                    activity.name
                )


                total_activity_minutes += (
                    activity
                    .estimated_duration_minutes
                )

                total_activity_cost += (
                    activity.estimated_cost
                    if activity.estimated_cost is not None
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
        activity.estimated_cost
        if activity.estimated_cost is not None
        else 0
    )
    for activity in activities
    if activity.name in selected_set
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

        total_activity_cost=round(
            total_selected_cost,
            2,
        ),

        activity_budget=(
            activity_budget
        ),

        objective_value=float(
            solution.ObjectiveValue()
        ),
    )