from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

_test_directory = tempfile.TemporaryDirectory()
os.environ["DEJ_DATABASE_PATH"] = str(Path(_test_directory.name) / "shop-test.sqlite3")
os.environ["DEJ_ADMIN_TOKEN"] = "test-admin-token-that-is-at-least-32-chars"

import backend


class StoreApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_directory = tempfile.TemporaryDirectory()
        backend.DATABASE_PATH = Path(self.database_directory.name) / "shop.sqlite3"
        backend.initialize_database()
        self.client = backend.app.test_client()
        self.admin_headers = {"X-Admin-Token": os.environ["DEJ_ADMIN_TOKEN"]}

    def tearDown(self) -> None:
        self.database_directory.cleanup()

    def test_stock_and_order_lifecycle(self) -> None:
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)

        products_response = self.client.get("/api/products")
        self.assertEqual(products_response.status_code, 200)
        products = products_response.get_json()
        self.assertEqual(len(products), 46)
        retro_jerseys = [product for product in products if product["id"].startswith("retro-")]
        self.assertEqual(len(retro_jerseys), 15)
        self.assertTrue(all(product["price"] == 24000 for product in retro_jerseys))
        self.assertFalse(any(product["id"] in backend.RETRO_DUPLICATE_PRODUCT_IDS for product in products))
        madrid = next(product for product in products if product["id"] == "real-madrid-dark-green")
        self.assertFalse(madrid["stockTracked"])

        unauthorized = self.client.get("/api/admin/products")
        self.assertEqual(unauthorized.status_code, 401)

        stock_update = self.client.patch(
            "/api/admin/products/real-madrid-dark-green/stock",
            headers=self.admin_headers,
            json={"stock": {"S": 3, "L": 2, "XL": 0, "XXL": None}},
        )
        self.assertEqual(stock_update.status_code, 200)
        self.assertEqual(stock_update.get_json()["availableSizes"], ["S", "L"])

        order_response = self.client.post(
            "/api/orders",
            json={
                "name": "Test Customer",
                "phone": "08000000000",
                "address": "Lagos",
                "items": [{
                    "product_id": "real-madrid-dark-green",
                    "size": "S",
                    "quantity": 2,
                    "badge": "premier-league",
                }],
            },
        )
        self.assertEqual(order_response.status_code, 201)
        order = order_response.get_json()
        self.assertEqual(order["subtotal"], 42000)
        self.assertEqual(order["status"], "pending_confirmation")

        confirmed = self.client.patch(
            f"/api/admin/orders/{order['reference']}",
            headers=self.admin_headers,
            json={"status": "confirmed"},
        )
        self.assertEqual(confirmed.status_code, 200)
        refreshed = self.client.get("/api/products").get_json()
        madrid = next(product for product in refreshed if product["id"] == "real-madrid-dark-green")
        self.assertEqual(madrid["stockBySize"]["S"], 1)

        cancelled = self.client.patch(
            f"/api/admin/orders/{order['reference']}",
            headers=self.admin_headers,
            json={"status": "cancelled"},
        )
        self.assertEqual(cancelled.status_code, 200)
        refreshed = self.client.get("/api/products").get_json()
        madrid = next(product for product in refreshed if product["id"] == "real-madrid-dark-green")
        self.assertEqual(madrid["stockBySize"]["S"], 3)

    def test_retro_jerseys_are_added_to_existing_database(self) -> None:
        connection = backend.connect_database()
        try:
            with connection:
                connection.execute("DELETE FROM inventory WHERE product_id LIKE 'retro-%'")
                connection.execute("DELETE FROM products WHERE id LIKE 'retro-%'")
        finally:
            connection.close()

        backend.initialize_database()
        products = self.client.get("/api/products").get_json()
        retro_jerseys = [product for product in products if product["id"].startswith("retro-")]
        self.assertEqual(len(retro_jerseys), 15)
        self.assertEqual(retro_jerseys[0]["image"], "images/Retro jersey/photo_1_2026-10-22_21-11-39.jpg")
        self.assertTrue(all(product["price"] == 24000 for product in retro_jerseys))

    def test_national_jerseys_reject_badges(self) -> None:
        response = self.client.post(
            "/api/orders",
            json={
                "name": "Test Customer",
                "phone": "08000000000",
                "address": "Lagos",
                "items": [{
                    "product_id": "national-new-01",
                    "size": "L",
                    "quantity": 1,
                    "badge": "champions-league",
                }],
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_retro_duplicate_jersey_cannot_be_ordered(self) -> None:
        duplicate_id = next(iter(backend.RETRO_DUPLICATE_PRODUCT_IDS))
        response = self.client.post(
            "/api/orders",
            json={
                "name": "Test Customer",
                "phone": "08000000000",
                "address": "Lagos",
                "items": [{
                    "product_id": duplicate_id,
                    "size": "L",
                    "quantity": 1,
                }],
            },
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()