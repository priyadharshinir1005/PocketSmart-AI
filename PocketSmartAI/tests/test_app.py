import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from google.genai import types

from app.config import settings
from app.main import app
from app.services.recommendations import recommendation_service


class PocketSmartAPITests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_database_path = settings.database_path
        self.old_api_key = settings.gemini_api_key
        settings.database_path = str(Path(self.temp_dir.name) / "test.sqlite3")
        settings.gemini_api_key = None
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        settings.database_path = self.old_database_path
        settings.gemini_api_key = self.old_api_key
        self.temp_dir.cleanup()

    def register(self):
        response = self.client.post("/register", json={
            "username": "budget_reader",
            "email": "reader@example.com",
            "password": "safe-passphrase-123",
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response

    def csrf_headers(self):
        token = self.client.cookies.get("pocketsmart_csrf")
        return {"X-CSRF-Token": token} if token else {}

    def test_pages_and_health(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("/static/app.css", home.text)
        self.assertEqual(self.client.get("/health").json()["status"], "ok")
        self.assertEqual(self.client.get("/dashboard").url.path, "/login")
        self.register()
        for route in ("/dashboard", "/planner/home", "/planner/party", "/planner/jewelry", "/history", "/testimonials"):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200, route)
                if route == "/planner/home":
                    self.assertIn("data-add-room", response.text)

    def test_registration_auth_and_logout(self):
        response = self.register()
        self.assertEqual(response.json()["user"]["username"], "budget_reader")
        self.assertEqual(self.client.get("/session-info").status_code, 200)
        duplicate = self.client.post("/register", json={
            "username": "budget_reader",
            "email": "other@example.com",
            "password": "safe-passphrase-123",
        })
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.client.post("/logout", headers=self.csrf_headers()).status_code, 200)
        self.assertEqual(self.client.get("/session-info").status_code, 401)

    def test_csrf_and_home_party_jewelry_plans_respect_budget(self):
        self.register()
        home = {
            "budget": 30000,
            "city": "Pune",
            "style": "warm minimal",
            "notes": "Easy to clean",
            "rooms": [
                {"name": "Living room", "items": [{"name": "Ceiling fan", "quantity": 2}, {"name": "Floor lamp", "quantity": 1}]},
                {"name": "Bedroom", "items": [{"name": "Bedside lamp", "quantity": 2}]},
            ],
        }
        denied = self.client.post("/generate-home", json=home)
        self.assertEqual(denied.status_code, 403)
        response = self.client.post("/generate-home", json=home, headers=self.csrf_headers())
        self.assertEqual(response.status_code, 200, response.text)
        home_plan = response.json()["plan"]
        self.assertLessEqual(home_plan["total_estimated"], home["budget"])
        self.assertEqual(len(home_plan["recommendations"]), 3)
        self.assertEqual(response.json()["source"], "local")
        self.assertTrue(home_plan["search_links"][0][0]["url"].startswith("https://"))

        party = self.client.post("/generate-party", json={
            "budget": 50000, "guests": 35, "event_type": "Birthday", "city": "Pune",
            "venue_preference": "Outdoor", "dietary_needs": "Vegetarian", "priorities": "Good food",
        }, headers=self.csrf_headers())
        self.assertEqual(party.status_code, 200, party.text)
        self.assertLessEqual(party.json()["plan"]["total_estimated"], 50000)

        png = b"\x89PNG\r\n\x1a\n" + b"test-image-bytes"
        jewelry = self.client.post("/generate-jewelry", data={
            "budget": "12000", "occasion": "Festive dinner", "style": "Modern traditional",
            "outfit_description": "Deep green outfit",
        }, files={"outfit_image": ("outfit.png", png, "image/png")}, headers=self.csrf_headers())
        self.assertEqual(jewelry.status_code, 200, jewelry.text)
        self.assertLessEqual(jewelry.json()["plan"]["total_estimated"], 12000)
        self.assertIn("Image analysis was unavailable", jewelry.json()["plan"]["image_observation"])

        history = self.client.get("/history", headers={"Accept": "application/json"})
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()["items"]), 3)
        rec_id = history.json()["items"][0]["id"]
        detail = self.client.get(f"/recommendations-details/{rec_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("plan", detail.json())

    def test_oauth_token_and_invalid_image_type(self):
        self.register()
        token = self.client.post("/token", data={"username": "budget_reader", "password": "safe-passphrase-123"})
        self.assertEqual(token.status_code, 200, token.text)
        bearer = {"Authorization": f"Bearer {token.json()['access_token']}"}
        response = self.client.post("/generate-jewelry", data={
            "budget": "8000", "occasion": "Dinner", "style": "Minimal",
        }, files={"outfit_image": ("not-an-image.png", b"no", "image/png")}, headers=bearer)
        self.assertEqual(response.status_code, 415)

    def test_gemini_json_and_image_request_shape(self):
        settings.gemini_api_key = "test-key"
        model_response = SimpleNamespace(text=json.dumps({
            "title": "A coordinated festive look",
            "summary": "A sample plan from the mocked Gemini response.",
            "budget_breakdown": [{"category": "Jewelry", "amount": 8000, "rationale": "Keep a reserve."}],
            "recommendations": [{
                "name": "Pearl drop earrings", "category": "Earrings", "description": "A light statement piece.",
                "estimated_unit_price": 4000, "quantity": 1, "platforms": ["Amazon"],
            }],
            "savings_tips": ["Compare materials."],
            "style_notes": ["Pair with a simple necklace."],
            "image_observation": "The outfit appears deep green.",
        }))
        fake_models = Mock()
        fake_models.generate_content.return_value = model_response
        fake_client = SimpleNamespace(models=fake_models)
        with patch("google.genai.Client", return_value=fake_client) as client_factory:
            result = recommendation_service.generate(
                "jewelry",
                {"budget": 12000, "occasion": "Festive dinner", "style": "Modern traditional", "outfit_description": "Green"},
                b"image-bytes",
                "image/png",
            )
        client_factory.assert_called_once_with(api_key="test-key")
        self.assertEqual(result["source"], "gemini")
        self.assertEqual(result["image_observation"], "The outfit appears deep green.")
        request_contents = fake_models.generate_content.call_args.kwargs["contents"]
        self.assertIsInstance(request_contents[1], types.Part)


if __name__ == "__main__":
    unittest.main()
