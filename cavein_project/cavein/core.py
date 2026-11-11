"""Inti Cavein: enum, skema SQLite, notifikasi, dan aturan hitung (hanya stdlib).

Uang disimpan sebagai integer rupiah: ringan, cepat, dan bebas error float.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime
from enum import Enum

TAX_RATE_PCT = 11      # PPN
SERVICE_RATE_PCT = 5   # service charge


class CaveinError(Exception):
    """Pelanggaran aturan bisnis atau input tidak valid."""


class PermissionDenied(CaveinError):
    """Role tidak punya hak untuk aksi tersebut."""


class _StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class OrderStatus(_StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    READY = "READY"
    SERVED = "SERVED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PaymentStatus(_StrEnum):
    UNPAID = "UNPAID"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentMethod(_StrEnum):
    CASH = "CASH"
    QRIS = "QRIS"
    EWALLET = "EWALLET"
    CARD = "CARD"


class TableStatus(_StrEnum):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    RESERVED = "RESERVED"


class Role(_StrEnum):
    ADMIN = "ADMIN"
    CASHIER = "CASHIER"
    KITCHEN = "KITCHEN"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _pct(amount: int, pct: int) -> int:
    return (amount * pct + 50) // 100  # pembulatan half-up, integer


def compute_totals(subtotal: int, discount: int = 0) -> tuple[int, int, int]:
    """Pajak & service dihitung otomatis dari subtotal. Return (tax, service, total)."""
    tax = _pct(subtotal, TAX_RATE_PCT)
    service = _pct(subtotal, SERVICE_RATE_PCT)
    discount = max(0, min(discount, subtotal))
    return tax, service, subtotal + tax + service - discount


def rupiah(n: int) -> str:
    return "Rp" + f"{n:,}".replace(",", ".")


class Notifier:
    """Pub/sub in-process. Pengganti WebSocket yang ringan; mudah dihubungkan ke SSE/WS nanti."""

    def __init__(self) -> None:
        self._subs: dict[str, list] = defaultdict(list)

    def subscribe(self, topic: str, fn) -> None:
        self._subs[topic].append(fn)

    def publish(self, topic: str, payload: dict) -> None:
        for fn in self._subs.get(topic, ()):
            fn(payload)


SCHEMA = """
CREATE TABLE IF NOT EXISTS outlet(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT);
INSERT OR IGNORE INTO outlet(id, name) VALUES (1, 'Cavein Pusat');

CREATE TABLE IF NOT EXISTS category(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, display_order INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS menu_item(
  id INTEGER PRIMARY KEY,
  category_id INTEGER NOT NULL REFERENCES category(id),
  name TEXT NOT NULL, description TEXT DEFAULT '', image_url TEXT DEFAULT '',
  price INTEGER NOT NULL CHECK(price >= 0),
  is_available INTEGER NOT NULL DEFAULT 1,
  is_vegetarian INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS menu_option(
  id INTEGER PRIMARY KEY,
  menu_item_id INTEGER NOT NULL REFERENCES menu_item(id),
  name TEXT NOT NULL, is_required INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS option_choice(
  id INTEGER PRIMARY KEY,
  menu_option_id INTEGER NOT NULL REFERENCES menu_option(id),
  label TEXT NOT NULL, extra_price INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS dining_table(
  id INTEGER PRIMARY KEY,
  outlet_id INTEGER NOT NULL DEFAULT 1 REFERENCES outlet(id),
  number INTEGER NOT NULL, capacity INTEGER NOT NULL DEFAULT 4,
  qr_code TEXT UNIQUE, status TEXT NOT NULL DEFAULT 'AVAILABLE',
  UNIQUE(outlet_id, number));

CREATE TABLE IF NOT EXISTS table_session(
  id INTEGER PRIMARY KEY,
  table_id INTEGER NOT NULL REFERENCES dining_table(id),
  opened_at TEXT NOT NULL, closed_at TEXT,
  status TEXT NOT NULL DEFAULT 'OPEN');
-- Aturan bisnis: satu meja hanya punya satu sesi aktif (dijaga di level DB).
CREATE UNIQUE INDEX IF NOT EXISTS one_open_session
  ON table_session(table_id) WHERE status = 'OPEN';

CREATE TABLE IF NOT EXISTS customer(
  id INTEGER PRIMARY KEY, name TEXT, phone TEXT, email TEXT);

CREATE TABLE IF NOT EXISTS voucher(
  id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE,
  discount_type TEXT NOT NULL CHECK(discount_type IN ('PERCENT','FIXED')),
  value INTEGER NOT NULL, min_purchase INTEGER NOT NULL DEFAULT 0,
  valid_from TEXT, valid_until TEXT, quota INTEGER NOT NULL DEFAULT 1);

CREATE TABLE IF NOT EXISTS staff(
  id INTEGER PRIMARY KEY,
  outlet_id INTEGER NOT NULL DEFAULT 1 REFERENCES outlet(id),
  name TEXT NOT NULL, username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL, role TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1);

CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY,
  order_number TEXT UNIQUE,
  session_id INTEGER NOT NULL REFERENCES table_session(id),
  customer_id INTEGER REFERENCES customer(id),
  voucher_id INTEGER REFERENCES voucher(id),
  confirmed_by INTEGER REFERENCES staff(id),
  status TEXT NOT NULL DEFAULT 'PENDING',
  subtotal INTEGER NOT NULL, tax INTEGER NOT NULL, service_charge INTEGER NOT NULL,
  discount INTEGER NOT NULL DEFAULT 0, total_amount INTEGER NOT NULL,
  cancel_reason TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id);

CREATE TABLE IF NOT EXISTS order_item(
  id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(id),
  menu_item_id INTEGER NOT NULL REFERENCES menu_item(id),
  quantity INTEGER NOT NULL CHECK(quantity > 0),
  unit_price INTEGER NOT NULL,      -- snapshot harga saat dipesan
  note TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'PENDING');
CREATE INDEX IF NOT EXISTS idx_order_item_order ON order_item(order_id);

CREATE TABLE IF NOT EXISTS order_item_choice(
  order_item_id INTEGER NOT NULL REFERENCES order_item(id),
  option_choice_id INTEGER NOT NULL REFERENCES option_choice(id),
  extra_price INTEGER NOT NULL,     -- snapshot
  PRIMARY KEY(order_item_id, option_choice_id));

CREATE TABLE IF NOT EXISTS payment(
  id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
  method TEXT NOT NULL, amount INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'UNPAID', paid_at TEXT, transaction_ref TEXT);

CREATE TABLE IF NOT EXISTS review(
  id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
  rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
  comment TEXT DEFAULT '', created_at TEXT NOT NULL);
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:":
        db.execute("PRAGMA journal_mode = WAL")  # baca/tulis bersamaan tanpa saling blokir
    db.executescript(SCHEMA)
    return db
