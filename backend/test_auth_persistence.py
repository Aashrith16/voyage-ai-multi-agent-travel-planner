import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch

import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from voyage_ai import auth, persistence
from voyage_ai.auth import AuthenticatedUser
from voyage_ai.api import app


class SupabaseAuthTests(unittest.TestCase):
    def setUp(self):
        self.user_id = str(uuid4())
        self.issuer = "https://example.supabase.co/auth/v1"
        self.env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_JWT_SECRET": "deterministic-test-secret-with-length-over-32",
            "VOYAGEAI_ENV": "production",
        }

    def _credentials(self, claims=None, secret=None):
        payload = {
            "sub": self.user_id,
            "iss": self.issuer,
            "aud": "authenticated",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        }
        payload.update(claims or {})
        token = jwt.encode(payload, secret or self.env["SUPABASE_JWT_SECRET"], algorithm="HS256")
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    def test_valid_supabase_hs256_token_returns_verified_subject(self):
        with patch.dict("os.environ", self.env, clear=False):
            user = auth.get_current_user(self._credentials({"email": "traveler@example.test"}))
        self.assertEqual(user, AuthenticatedUser(id=self.user_id, email="traveler@example.test"))

    def test_wrong_issuer_or_audience_is_rejected(self):
        for claim in ({"iss": "https://other.example/auth/v1"}, {"aud": "anon"}):
            with self.subTest(claim=claim), patch.dict("os.environ", self.env, clear=False):
                with self.assertRaises(HTTPException) as error:
                    auth.get_current_user(self._credentials(claim))
                self.assertEqual(error.exception.status_code, 401)

    def test_token_signed_by_a_different_secret_is_rejected(self):
        credentials = self._credentials(secret="not-the-project-secret-with-length-over-32")
        with patch.dict("os.environ", self.env, clear=False):
            with self.assertRaises(HTTPException) as error:
                auth.get_current_user(credentials)
        self.assertEqual(error.exception.status_code, 401)

    def test_local_development_uses_only_the_local_development_identity(self):
        env = {"VOYAGEAI_ENV": "development"}
        with patch.dict("os.environ", env, clear=True):
            user = auth.get_current_user(None)
        self.assertEqual(user.id, "00000000-0000-4000-8000-000000000001")

    def test_missing_supabase_configuration_fails_closed_outside_development(self):
        with patch.dict("os.environ", {"VOYAGEAI_ENV": "production"}, clear=True):
            with self.assertRaises(HTTPException) as error:
                auth.get_current_user(None)
        self.assertEqual(error.exception.status_code, 503)

    def test_private_trip_api_requires_a_bearer_token(self):
        with patch.dict("os.environ", self.env, clear=False):
            response = TestClient(app).get("/api/trips")
        self.assertEqual(response.status_code, 401)


class TripOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.old_pool = persistence._pool
        persistence._pool = None
        persistence._memory_trips.clear()
        self.owner_id = str(uuid4())
        self.other_user = str(uuid4())
        self.trip_id = str(uuid4())
        self.thread_id = str(uuid4())

    def tearDown(self):
        persistence._memory_trips.clear()
        persistence._pool = self.old_pool

    def test_owned_trip_survives_repository_reload_and_lists_only_owner(self):
        saved = persistence.save_trip(
            self.owner_id, self.trip_id, self.thread_id, "budget_review",
            {"status": "budget_review", "final_trip": {"destination": "Kyoto"}},
        )
        self.assertEqual(saved["trip_id"], self.trip_id)
        self.assertEqual(persistence.get_trip(self.owner_id, self.trip_id)["data"]["status"], "budget_review")
        self.assertEqual(len(persistence.list_trips(self.owner_id)), 1)
        self.assertEqual(persistence.list_trips(self.other_user), [])

    def test_another_account_cannot_read_or_resume_a_trip_by_id_or_thread(self):
        persistence.save_trip(self.owner_id, self.trip_id, self.thread_id, "budget_review", {})
        for operation in (
            lambda: persistence.get_trip(self.other_user, self.trip_id),
            lambda: persistence.get_trip_by_thread(self.other_user, self.thread_id),
        ):
            with self.assertRaises(HTTPException) as error:
                operation()
            self.assertEqual(error.exception.status_code, 404)

    def test_another_account_cannot_claim_an_existing_thread(self):
        persistence.save_trip(self.owner_id, self.trip_id, self.thread_id, "processing", {})
        with self.assertRaises(HTTPException) as error:
            persistence.save_trip(self.other_user, str(uuid4()), self.thread_id, "complete", {})
        self.assertEqual(error.exception.status_code, 404)

    def test_production_database_setup_refuses_process_local_storage(self):
        with patch.dict("os.environ", {"VOYAGEAI_ENV": "production"}, clear=True):
            with self.assertRaises(RuntimeError):
                persistence.initialize_database()


if __name__ == "__main__":
    unittest.main()
