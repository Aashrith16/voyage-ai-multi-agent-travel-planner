"""Persistent ownership records for saved VoyageAI trips.

In local development the repository is process-local so the application can be
run without a Supabase project. Production requires Supabase Postgres; the graph
checkpointer and trip table then share the same managed connection pool.
"""

from __future__ import annotations

import json
import os
from threading import RLock
from typing import Any
from uuid import UUID

from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

_pool = None
_memory_trips: dict[str, dict[str, Any]] = {}
_memory_lock = RLock()


def _production_mode() -> bool:
    return os.getenv("VOYAGEAI_ENV", "development").casefold() in {"production", "prod"} or bool(os.getenv("RENDER"))


def initialize_database():
    """Create the shared pool and owner-protected trip table when configured."""
    global _pool
    database_url = os.getenv("SUPABASE_DB_URL")
    if not database_url:
        if _production_mode():
            raise RuntimeError("SUPABASE_DB_URL is required outside local development.")
        return None

    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=int(os.getenv("DATABASE_POOL_SIZE", "8")),
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=False,
    )
    pool.open(wait=True)
    with pool.connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS public.voyage_trips (
                trip_id uuid PRIMARY KEY,
                owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
                thread_id text NOT NULL UNIQUE,
                status text NOT NULL,
                destination text,
                origin text,
                departure_date date,
                return_date date,
                travelers integer,
                total_budget numeric,
                currency text,
                trip_data jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS voyage_trips_owner_updated_idx "
            "ON public.voyage_trips (owner_id, updated_at DESC)"
        )
        connection.execute("ALTER TABLE public.voyage_trips ENABLE ROW LEVEL SECURITY")
    _pool = pool
    return pool


def database_pool():
    return _pool


def _owner_uuid(owner_id: str) -> str:
    try:
        return str(UUID(owner_id))
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(status_code=401, detail="The authenticated account ID is invalid.") from error


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("trip_data") or {}
    trip = data.get("final_trip") or {}
    return {
        "trip_id": str(row["trip_id"]),
        "thread_id": row["thread_id"],
        "status": row["status"],
        "destination": trip.get("destination") or row.get("destination"),
        "origin": trip.get("origin") or row.get("origin"),
        "departure_date": trip.get("departure_date") or row.get("departure_date"),
        "return_date": trip.get("return_date") or row.get("return_date"),
        "travelers": trip.get("travelers") or row.get("travelers"),
        "budget": trip.get("budget") or row.get("total_budget"),
        "currency": trip.get("currency") or row.get("currency"),
        "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
        "data": data,
    }


def save_trip(owner_id: str, trip_id: str, thread_id: str, status: str, data: dict[str, Any]) -> dict[str, Any]:
    owner_id = _owner_uuid(owner_id)
    trip_id = str(UUID(trip_id))
    trip = data.get("final_trip") or {}
    if _pool is None:
        with _memory_lock:
            existing = _memory_trips.get(thread_id)
            if existing and existing["owner_id"] != owner_id:
                raise HTTPException(status_code=404, detail="Trip not found.")
            record = {
                "trip_id": existing["trip_id"] if existing else trip_id,
                "owner_id": owner_id,
                "thread_id": thread_id,
                "status": status,
                "destination": trip.get("destination"),
                "origin": trip.get("origin"),
                "departure_date": trip.get("departure_date"),
                "return_date": trip.get("return_date"),
                "travelers": trip.get("travelers"),
                "total_budget": trip.get("budget"),
                "currency": trip.get("currency"),
                "trip_data": data,
                "updated_at": None,
            }
            _memory_trips[thread_id] = record
            return _summary(record)

    with _pool.connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO public.voyage_trips
                (trip_id, owner_id, thread_id, status, destination, origin,
                 departure_date, return_date, travelers, total_budget, currency, trip_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (thread_id) DO UPDATE SET
                status = EXCLUDED.status,
                destination = EXCLUDED.destination,
                origin = EXCLUDED.origin,
                departure_date = EXCLUDED.departure_date,
                return_date = EXCLUDED.return_date,
                travelers = EXCLUDED.travelers,
                total_budget = EXCLUDED.total_budget,
                currency = EXCLUDED.currency,
                trip_data = EXCLUDED.trip_data,
                updated_at = now()
            WHERE public.voyage_trips.owner_id = EXCLUDED.owner_id
            RETURNING trip_id, thread_id, status, destination, origin,
                      departure_date, return_date, travelers, total_budget,
                      currency, trip_data, updated_at
            """,
            (
                trip_id, owner_id, thread_id, status, trip.get("destination"),
                trip.get("origin"), trip.get("departure_date"), trip.get("return_date"),
                trip.get("travelers"), trip.get("budget"), trip.get("currency"),
                json.dumps(data, ensure_ascii=False),
            ),
        )
        row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Trip not found.")
    keys = ["trip_id", "thread_id", "status", "destination", "origin", "departure_date", "return_date", "travelers", "total_budget", "currency", "trip_data", "updated_at"]
    return _summary(dict(zip(keys, row)))


def get_trip(owner_id: str, trip_id: str) -> dict[str, Any]:
    owner_id = _owner_uuid(owner_id)
    if _pool is None:
        with _memory_lock:
            record = next((item for item in _memory_trips.values() if item["trip_id"] == str(trip_id) and item["owner_id"] == owner_id), None)
        if record is None:
            raise HTTPException(status_code=404, detail="Trip not found.")
        return _summary(record)
    with _pool.connection() as connection:
        cursor = connection.execute(
            "SELECT trip_id, thread_id, status, destination, origin, departure_date, return_date, travelers, total_budget, currency, trip_data, updated_at "
            "FROM public.voyage_trips WHERE trip_id = %s AND owner_id = %s",
            (trip_id, owner_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Trip not found.")
    keys = ["trip_id", "thread_id", "status", "destination", "origin", "departure_date", "return_date", "travelers", "total_budget", "currency", "trip_data", "updated_at"]
    return _summary(dict(zip(keys, row)))


def get_trip_by_thread(owner_id: str, thread_id: str) -> dict[str, Any]:
    owner_id = _owner_uuid(owner_id)
    if _pool is None:
        with _memory_lock:
            record = _memory_trips.get(thread_id)
            if record is None or record["owner_id"] != owner_id:
                raise HTTPException(status_code=404, detail="Trip not found.")
            return _summary(record)
    with _pool.connection() as connection:
        cursor = connection.execute(
            "SELECT trip_id, thread_id, status, destination, origin, departure_date, return_date, travelers, total_budget, currency, trip_data, updated_at "
            "FROM public.voyage_trips WHERE thread_id = %s AND owner_id = %s",
            (thread_id, owner_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Trip not found.")
    keys = ["trip_id", "thread_id", "status", "destination", "origin", "departure_date", "return_date", "travelers", "total_budget", "currency", "trip_data", "updated_at"]
    return _summary(dict(zip(keys, row)))


def list_trips(owner_id: str) -> list[dict[str, Any]]:
    owner_id = _owner_uuid(owner_id)
    if _pool is None:
        with _memory_lock:
            records = [item for item in _memory_trips.values() if item["owner_id"] == owner_id]
        return [
            {key: value for key, value in _summary(record).items() if key != "data"}
            for record in sorted(records, key=lambda item: item.get("updated_at") or "", reverse=True)
        ]
    with _pool.connection() as connection:
        cursor = connection.execute(
            "SELECT trip_id, thread_id, status, destination, origin, departure_date, return_date, travelers, total_budget, currency, trip_data, updated_at "
            "FROM public.voyage_trips WHERE owner_id = %s ORDER BY updated_at DESC",
            (owner_id,),
        )
        rows = cursor.fetchall()
    keys = ["trip_id", "thread_id", "status", "destination", "origin", "departure_date", "return_date", "travelers", "total_budget", "currency", "trip_data", "updated_at"]
    return [
        {key: value for key, value in _summary(dict(zip(keys, row))).items() if key != "data"}
        for row in rows
    ]
