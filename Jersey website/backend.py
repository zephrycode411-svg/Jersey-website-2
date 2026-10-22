from __future__ import annotations

import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Flask, g, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get("DEJ_DATABASE_PATH", BASE_DIR / "instance" / "store.sqlite3"))
ADMIN_TOKEN = os.environ.get("DEJ_ADMIN_TOKEN", "")
SIZES = ("S", "L", "XL", "XXL")
BADGE_PRICE = 3000
RETRO_DUPLICATE_TELEGRAM_NUMBERS = frozenset({1, 2, 3, 4, 5, 7, 10, 15, 16, 17, 26, 29, 30, 31, 35})
RETRO_DUPLICATE_PRODUCT_IDS = frozenset(
    f"telegram-{number:02d}" for number in RETRO_DUPLICATE_TELEGRAM_NUMBERS
)


def build_catalog() -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []

    for number in range(1, 36):
        if number in RETRO_DUPLICATE_TELEGRAM_NUMBERS:
            continue
        is_england = number in (8, 19)
        is_spain = number == 23
        is_nigeria = number == 32
        is_national = is_england or is_spain or is_nigeria
        if is_england:
            name = f"England National Team Shirt {'01' if number == 8 else '02'}"
            team = "England"
        elif is_spain:
            name, team = "Spain National Team Shirt 01", "Spain"
        elif is_nigeria:
            name, team = "Nigeria National Team Jersey", "Nigeria"
        else:
            name, team = f"Club Jersey {number:02d}", "Club selection"

        products.append({
            "id": f"telegram-{number:02d}",
            "sku": f"DEJ-{number:04d}",
            "name": name,
            "team": team,
            "category": "national" if is_national else "club",
            "price": 18000,
            "currency": "NGN",
            "image": f"images/jerseys/photo_{number}_2026-10-17_00-41-31.jpg",
            "isNewArrival": number >= 30 or is_national,
            "source": "telegram-import",
        })

    new_national = [
        ("Brazil", "Brazil National Team Away Jersey"),
        ("France", "France National Team Jersey"),
        ("Brazil", "Brazil National Team Home Jersey"),
        ("Morocco", "Morocco National Team Away Jersey"),
        ("Morocco", "Morocco National Team Home Jersey"),
        ("Brazil", "Brazil National Team Jersey and Shorts Set"),
        ("Germany", "Germany National Team Jersey"),
        ("Argentina", "Argentina National Team Jersey"),
        ("England", "England National Team Red Away Jersey"),
        ("Italy", "Italy National Team Jersey"),
    ]
    for number, (team, name) in enumerate(new_national, start=1):
        products.append({
            "id": f"national-new-{number:02d}",
            "sku": f"DEJ-NT-{number:04d}",
            "name": name,
            "team": team,
            "category": "national",
            "price": 18000,
            "currency": "NGN",
            "image": f"images/jerseys/photo_{number}_2026-10-17_10-44-53.jpg",
            "isNewArrival": True,
            "source": "user-upload",
        })

    products.append({
        "id": "real-madrid-dark-green",
        "sku": "DEJ-RM-GREEN-01",
        "name": "Real Madrid Dark Green Jersey",
        "team": "Real Madrid",
        "category": "club",
        "price": 18000,
        "currency": "NGN",
        "image": "images/real-madrid-jersey.jpg",
        "isNewArrival": True,
        "source": "user-upload",
    })

    for number in range(1, 16):
        products.append({
            "id": f"retro-{number:02d}",
            "sku": f"DEJ-RETRO-{number:04d}",
            "name": f"Retro Jersey {number:02d}",
            "team": "Retro collection",
            "category": "club",
            "price": 24000,
            "currency": "NGN",
            "image": f"images/Retro jersey/photo_{number}_2026-10-22_21-11-39.jpg",
            "isNewArrival": False,
            "source": "user-upload",
        })
    return products


PRODUCT_CATALOG = build_catalog()
app = Flask(__name__, static_folder=None)
app.config["JSON_SORT_KEYS"] = False


def connect_database() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_database() -> sqlite3.Connection:
    if "database" not in g:
        g.database = connect_database()
    return g.database


@app.teardown_appcontext
def close_database(_error: BaseException | None) -> None:
    connection = g.pop("database", None)
    if connection is not None:
        connection.close()


def initialize_database() -> None:
    connection = connect_database()
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                sku TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                team TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN ('club', 'national')),
                price INTEGER NOT NULL CHECK (price >= 0),
                currency TEXT NOT NULL,
                image TEXT NOT NULL,
                is_new_arrival INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS inventory (
                product_id TEXT NOT NULL REFERENCES products(id),
                size TEXT NOT NULL CHECK (size IN ('S', 'L', 'XL', 'XXL')),
                quantity INTEGER CHECK (quantity IS NULL OR quantity >= 0),
                PRIMARY KEY (product_id, size)
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference TEXT NOT NULL UNIQUE,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                delivery_address TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_confirmation',
                subtotal INTEGER NOT NULL CHECK (subtotal >= 0),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL REFERENCES products(id),
                product_name TEXT NOT NULL,
                sku TEXT NOT NULL,
                size TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                badge TEXT NOT NULL,
                badge_text TEXT NOT NULL DEFAULT '',
                unit_price INTEGER NOT NULL CHECK (unit_price >= 0)
            );
            CREATE INDEX IF NOT EXISTS orders_status_created ON orders(status, created_at);
            """
        )
        with connection:
            for product in PRODUCT_CATALOG:
                connection.execute(
                    """INSERT OR IGNORE INTO products
                       (id, sku, name, team, category, price, currency, image, is_new_arrival, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        product["id"], product["sku"], product["name"], product["team"],
                        product["category"], product["price"], product["currency"],
                        product["image"], int(product["isNewArrival"]), product["source"],
                    ),
                )
                connection.executemany(
                    "INSERT OR IGNORE INTO inventory (product_id, size, quantity) VALUES (?, ?, NULL)",
                    [(product["id"], size) for size in SIZES],
                )
    finally:
        connection.close()


def admin_required(handler: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(handler)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if len(ADMIN_TOKEN) < 32:
            return jsonify({"error": "Admin access is disabled until DEJ_ADMIN_TOKEN is configured with a 32-character secret."}), 503
        supplied = request.headers.get("X-Admin-Token", "")
        if not hmac.compare_digest(supplied, ADMIN_TOKEN):
            return jsonify({"error": "Admin authorization failed."}), 401
        return handler(*args, **kwargs)
    return wrapped


def product_from_row(row: sqlite3.Row, connection: sqlite3.Connection) -> dict[str, Any]:
    product = dict(row)
    product["isNewArrival"] = bool(product.pop("is_new_arrival"))
    product["stockBySize"] = {
        stock["size"]: stock["quantity"]
        for stock in connection.execute(
            "SELECT size, quantity FROM inventory WHERE product_id = ?", (product["id"],)
        )
    }
    tracked_sizes = [size for size, quantity in product["stockBySize"].items() if quantity is not None]
    product["stockTracked"] = bool(tracked_sizes)
    product["availableSizes"] = (
        [size for size in SIZES if (product["stockBySize"].get(size) or 0) > 0]
        if tracked_sizes else list(SIZES)
    )
    return product


def json_error(message: str, status: int) -> tuple[Any, int]:
    return jsonify({"error": message}), status


@app.get("/api/health")
def health() -> Any:
    return jsonify({"status": "ok", "service": "desmond-empire-jerseys"})


@app.get("/api/products")
def list_products() -> Any:
    connection = get_database()
    placeholders = ", ".join("?" for _ in RETRO_DUPLICATE_PRODUCT_IDS)
    rows = connection.execute(
        f"SELECT * FROM products WHERE id NOT IN ({placeholders}) ORDER BY sku",
        tuple(RETRO_DUPLICATE_PRODUCT_IDS),
    ).fetchall()
    return jsonify([product_from_row(row, connection) for row in rows])


@app.post("/api/orders")
def create_order() -> Any:
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    address = str(data.get("address", "")).strip()
    items = data.get("items")
    if not name or len(name) > 100:
        return json_error("Enter a name up to 100 characters.", 400)
    if not phone or len(phone) > 40:
        return json_error("Enter a valid phone number.", 400)
    if not address or len(address) > 500:
        return json_error("Enter a delivery address up to 500 characters.", 400)
    if not isinstance(items, list) or not items or len(items) > 30:
        return json_error("Add between 1 and 30 order lines.", 400)

    connection = get_database()
    order_lines: list[dict[str, Any]] = []
    requested_stock: dict[tuple[str, str], int] = {}
    subtotal = 0
    for item in items:
        if not isinstance(item, dict):
            return json_error("Each order line must be an object.", 400)
        product_id = str(item.get("product_id", ""))
        if product_id in RETRO_DUPLICATE_PRODUCT_IDS:
            return json_error("This duplicate jersey is no longer available. Choose its Retro collection listing instead.", 404)
        size = str(item.get("size", ""))
        quantity = item.get("quantity")
        badge = str(item.get("badge", "none"))
        badge_text = str(item.get("custom_text", "")).strip()
        if size not in SIZES or not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= 100:
            return json_error("Each order line needs a supported size and quantity from 1 to 100.", 400)
        product_row = connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if product_row is None:
            return json_error("A selected jersey could not be found.", 404)
        product = dict(product_row)
        if badge not in {"none", "premier-league", "champions-league", "custom"}:
            return json_error("Choose a valid badge option.", 400)
        if product["category"] == "national" and badge != "none":
            return json_error("Badge customization is not available for national-team jerseys.", 400)
        if product["category"] == "club" and badge == "custom" and (not badge_text or len(badge_text) > 100):
            return json_error("Describe the custom badge in 1 to 100 characters.", 400)

        stock = connection.execute(
            "SELECT quantity FROM inventory WHERE product_id = ? AND size = ?", (product_id, size)
        ).fetchone()
        if stock is None:
            return json_error("Stock information for this size is unavailable.", 409)
        if stock["quantity"] is not None and stock["quantity"] < quantity:
            return json_error(f"Not enough stock for {product['name']} in size {size}.", 409)

        requested_stock[(product_id, size)] = requested_stock.get((product_id, size), 0) + quantity
        badge_price = BADGE_PRICE if product["category"] == "club" and badge != "none" else 0
        unit_price = product["price"] + badge_price
        subtotal += unit_price * quantity
        order_lines.append({
            "product": product,
            "size": size,
            "quantity": quantity,
            "badge": badge,
            "badge_text": badge_text if badge == "custom" else "",
            "unit_price": unit_price,
        })

    for (product_id, size), quantity in requested_stock.items():
        stock = connection.execute(
            "SELECT quantity FROM inventory WHERE product_id = ? AND size = ?", (product_id, size)
        ).fetchone()
        if stock["quantity"] is not None and stock["quantity"] < quantity:
            return json_error("Requested quantity exceeds the remaining stock for a jersey size.", 409)

    reference = f"DEJ-{secrets.token_hex(4).upper()}"
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connection:
        cursor = connection.execute(
            """INSERT INTO orders (reference, customer_name, customer_phone, delivery_address, subtotal, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (reference, name, phone, address, subtotal, created_at),
        )
        order_id = cursor.lastrowid
        connection.executemany(
            """INSERT INTO order_items
               (order_id, product_id, product_name, sku, size, quantity, badge, badge_text, unit_price)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (order_id, line["product"]["id"], line["product"]["name"], line["product"]["sku"],
                 line["size"], line["quantity"], line["badge"], line["badge_text"], line["unit_price"])
                for line in order_lines
            ],
        )
    return jsonify({"reference": reference, "status": "pending_confirmation", "subtotal": subtotal}), 201


@app.get("/api/admin/products")
@admin_required
def admin_products() -> Any:
    connection = get_database()
    placeholders = ", ".join("?" for _ in RETRO_DUPLICATE_PRODUCT_IDS)
    rows = connection.execute(
        f"SELECT * FROM products WHERE id NOT IN ({placeholders}) ORDER BY sku",
        tuple(RETRO_DUPLICATE_PRODUCT_IDS),
    ).fetchall()
    return jsonify([product_from_row(row, connection) for row in rows])


@app.patch("/api/admin/products/<path:product_id>/stock")
@admin_required
def update_stock(product_id: str) -> Any:
    data = request.get_json(silent=True) or {}
    stock_data = data.get("stock")
    if not isinstance(stock_data, dict) or not stock_data:
        return json_error("Provide size quantities in a stock object.", 400)
    connection = get_database()
    if connection.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone() is None:
        return json_error("Product not found.", 404)
    updates: list[tuple[str, int | None]] = []
    for size, quantity in stock_data.items():
        if size not in SIZES:
            return json_error(f"Unsupported size: {size}.", 400)
        if quantity is not None and (not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0):
            return json_error("Stock quantities must be non-negative whole numbers or null for untracked stock.", 400)
        updates.append((size, quantity))
    with connection:
        for size, quantity in updates:
            connection.execute(
                "UPDATE inventory SET quantity = ? WHERE product_id = ? AND size = ?",
                (quantity, product_id, size),
            )
    row = connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return jsonify(product_from_row(row, connection))


@app.get("/api/admin/orders")
@admin_required
def admin_orders() -> Any:
    connection = get_database()
    orders = connection.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 200").fetchall()
    result: list[dict[str, Any]] = []
    for order_row in orders:
        order = dict(order_row)
        order["items"] = [dict(row) for row in connection.execute(
            "SELECT product_name, sku, size, quantity, badge, badge_text, unit_price FROM order_items WHERE order_id = ?",
            (order["id"],),
        )]
        result.append(order)
    return jsonify(result)


@app.patch("/api/admin/orders/<reference>")
@admin_required
def update_order(reference: str) -> Any:
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if new_status not in {"confirmed", "dispatched", "completed", "cancelled"}:
        return json_error("Choose a supported order status.", 400)
    connection = get_database()
    order = connection.execute("SELECT * FROM orders WHERE reference = ?", (reference,)).fetchone()
    if order is None:
        return json_error("Order not found.", 404)

    current_status = order["status"]
    allowed_transitions = {
        "pending_confirmation": {"confirmed", "cancelled"},
        "confirmed": {"dispatched", "cancelled"},
        "dispatched": {"completed"},
        "completed": set(),
        "cancelled": set(),
    }
    if new_status not in allowed_transitions[current_status]:
        return json_error(f"Cannot move an order from {current_status} to {new_status}.", 409)

    lines = connection.execute("SELECT * FROM order_items WHERE order_id = ?", (order["id"],)).fetchall()
    try:
        with connection:
            if new_status == "confirmed":
                needed: dict[tuple[str, str], int] = {}
                for line in lines:
                    key = (line["product_id"], line["size"])
                    needed[key] = needed.get(key, 0) + line["quantity"]
                for (product_id, size), quantity in needed.items():
                    stock = connection.execute(
                        "SELECT quantity FROM inventory WHERE product_id = ? AND size = ?",
                        (product_id, size),
                    ).fetchone()
                    if stock is None or stock["quantity"] is None:
                        raise ValueError("Enter tracked stock for every ordered size before confirming this order.")
                    if stock["quantity"] < quantity:
                        raise ValueError(f"Not enough stock in size {size} to confirm this order.")
                for (product_id, size), quantity in needed.items():
                    connection.execute(
                        "UPDATE inventory SET quantity = quantity - ? WHERE product_id = ? AND size = ?",
                        (quantity, product_id, size),
                    )
            elif new_status == "cancelled" and current_status == "confirmed":
                for line in lines:
                    connection.execute(
                        "UPDATE inventory SET quantity = quantity + ? WHERE product_id = ? AND size = ? AND quantity IS NOT NULL",
                        (line["quantity"], line["product_id"], line["size"]),
                    )
            connection.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order["id"]))
    except ValueError as error:
        return json_error(str(error), 409)
    return jsonify({"reference": reference, "status": new_status})


@app.get("/")
def home() -> Any:
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/<path:asset_path>")
def serve_site_asset(asset_path: str) -> Any:
    return send_from_directory(BASE_DIR, asset_path)


initialize_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)