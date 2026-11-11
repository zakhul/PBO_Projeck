"""Modul Meja, Staf, dan Dapur — Muhammad Wafa. FR-01, FR-15, FR-16, FR-17, FR-18, FR-20, FR-21."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3

from .core import CaveinError, OrderStatus as S, PermissionDenied, Role, TableStatus, now
from .menu import MenuService
from .orders import OrderService

QR_BASE_URL = "https://cavein.example/m/"  # isi QR code; render gambarnya dengan generator QR apa pun


class TableService:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def add_table(self, number: int, capacity: int = 4, outlet_id: int = 1) -> int:
        token = secrets.token_urlsafe(8)
        try:
            with self.db:
                cur = self.db.execute(
                    "INSERT INTO dining_table(outlet_id, number, capacity, qr_code) VALUES (?,?,?,?)",
                    (outlet_id, number, capacity, token))
        except sqlite3.IntegrityError:
            raise CaveinError(f"Meja {number} sudah ada") from None
        return cur.lastrowid

    def qr_payload(self, table_id: int) -> str:
        row = self.db.execute("SELECT qr_code FROM dining_table WHERE id=?", (table_id,)).fetchone()
        if row is None:
            raise CaveinError("Meja tidak ditemukan")
        return QR_BASE_URL + row["qr_code"]

    def scan(self, qr: str) -> tuple[int, int]:
        """Scan QR: nomor meja terdeteksi otomatis. Return (table_id, session_id); sesi dibuka bila belum ada."""
        token = qr.removeprefix(QR_BASE_URL)
        t = self.db.execute("SELECT id FROM dining_table WHERE qr_code=?", (token,)).fetchone()
        if t is None:
            raise CaveinError("QR code tidak dikenali")
        with self.db:
            s = self.db.execute(
                "SELECT id FROM table_session WHERE table_id=? AND status='OPEN'", (t["id"],)).fetchone()
            if s is None:
                sid = self.db.execute(
                    "INSERT INTO table_session(table_id, opened_at) VALUES (?,?)", (t["id"], now())).lastrowid
                self.db.execute("UPDATE dining_table SET status=? WHERE id=?",
                                (TableStatus.OCCUPIED.value, t["id"]))
            else:
                sid = s["id"]
        return t["id"], sid

    def bill(self, session_id: int) -> int:
        """Satu meja = satu tagihan: total semua pesanan aktif di sesi tersebut."""
        return self.db.execute(
            "SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE session_id=? AND status!='CANCELLED'",
            (session_id,)).fetchone()[0]

    def close_session(self, session_id: int) -> None:
        s = self.db.execute("SELECT table_id, status FROM table_session WHERE id=?", (session_id,)).fetchone()
        if s is None or s["status"] != "OPEN":
            raise CaveinError("Sesi tidak aktif")
        pending = self.db.execute(
            "SELECT COUNT(*) FROM orders WHERE session_id=? AND status NOT IN ('COMPLETED','CANCELLED')",
            (session_id,)).fetchone()[0]
        if pending:
            raise CaveinError(f"Masih ada {pending} pesanan yang belum dibayar/disajikan")
        with self.db:
            self.db.execute("UPDATE table_session SET status='CLOSED', closed_at=? WHERE id=?",
                            (now(), session_id))
            self.db.execute("UPDATE dining_table SET status=? WHERE id=?",
                            (TableStatus.AVAILABLE.value, s["table_id"]))


PERMISSIONS = {
    Role.ADMIN: {"*"},
    Role.CASHIER: {"order.confirm", "order.cancel", "payment.process", "voucher.apply", "session.close"},
    Role.KITCHEN: {"kitchen.view", "kitchen.update", "menu.soldout"},
}


class AuthService:
    _ITER = 120_000  # cukup kuat, tetap ringan untuk device kecil

    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    @classmethod
    def _hash(cls, password: str, salt: bytes) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, cls._ITER).hex()

    def create_staff(self, name: str, username: str, password: str, role: Role | str,
                     outlet_id: int = 1) -> int:
        if len(password) < 6:
            raise CaveinError("Password minimal 6 karakter")
        salt = secrets.token_bytes(16)
        stored = salt.hex() + "$" + self._hash(password, salt)
        try:
            with self.db:
                cur = self.db.execute(
                    "INSERT INTO staff(outlet_id, name, username, password_hash, role) VALUES (?,?,?,?,?)",
                    (outlet_id, name, username, stored, Role(role).value))
        except sqlite3.IntegrityError:
            raise CaveinError("Username sudah dipakai") from None
        return cur.lastrowid

    def login(self, username: str, password: str) -> sqlite3.Row | None:
        row = self.db.execute(
            "SELECT * FROM staff WHERE username=? AND is_active=1", (username,)).fetchone()
        if row is None:
            return None
        salt_hex, digest = row["password_hash"].split("$")
        ok = hmac.compare_digest(self._hash(password, bytes.fromhex(salt_hex)), digest)
        return row if ok else None

    @staticmethod
    def can(role: Role | str, action: str) -> bool:
        perms = PERMISSIONS[Role(role)]
        return "*" in perms or action in perms

    def require(self, role: Role | str, action: str) -> None:
        if not self.can(role, action):
            raise PermissionDenied(f"Role {role} tidak boleh melakukan '{action}'")


class KitchenDisplayService:
    def __init__(self, db: sqlite3.Connection, orders: OrderService, menu: MenuService) -> None:
        self.db = db
        self.orders = orders
        self.menu = menu

    def queue(self) -> list[dict]:
        """Antrean dapur berurutan (terlama dulu), 2 query saja tanpa N+1."""
        orders = self.db.execute(
            "SELECT o.id, o.order_number, o.status, t.number AS table_number FROM orders o"
            " JOIN table_session s ON s.id=o.session_id JOIN dining_table t ON t.id=s.table_id"
            " WHERE o.status IN ('CONFIRMED','PREPARING') ORDER BY o.created_at, o.id").fetchall()
        if not orders:
            return []
        marks = ",".join("?" * len(orders))
        items = self.db.execute(
            f"SELECT oi.id, oi.order_id, mi.name, oi.quantity, oi.note, oi.status,"
            f" (SELECT GROUP_CONCAT(oc.label, ', ') FROM order_item_choice c"
            f"  JOIN option_choice oc ON oc.id=c.option_choice_id WHERE c.order_item_id=oi.id) AS options"
            f" FROM order_item oi JOIN menu_item mi ON mi.id=oi.menu_item_id"
            f" WHERE oi.order_id IN ({marks}) AND oi.status!='CANCELLED' ORDER BY oi.id",
            [o["id"] for o in orders]).fetchall()
        by_order: dict[int, list] = {}
        for it in items:
            by_order.setdefault(it["order_id"], []).append(dict(it))
        return [{**dict(o), "items": by_order.get(o["id"], [])} for o in orders]

    def set_item_status(self, item_id: int, status: S) -> None:
        status = S(status)
        step = {S.PREPARING: "CONFIRMED", S.READY: "PREPARING"}
        if status not in step:
            raise CaveinError("Dapur hanya mengubah status ke PREPARING atau READY")
        item = self.db.execute("SELECT order_id, status FROM order_item WHERE id=?", (item_id,)).fetchone()
        if item is None:
            raise CaveinError("Item tidak ditemukan")
        if item["status"] != step[status]:
            raise CaveinError(f"Item berstatus {item['status']}, tidak bisa menjadi {status}")
        with self.db:
            self.db.execute("UPDATE order_item SET status=? WHERE id=?", (status.value, item_id))
        self._sync_order(item["order_id"])

    def _sync_order(self, order_id: int) -> None:
        """Status pesanan mengikuti status item-itemnya."""
        states = {r[0] for r in self.db.execute(
            "SELECT status FROM order_item WHERE order_id=? AND status!='CANCELLED'", (order_id,))}
        cur = S(self.orders.get(order_id)["status"])
        if cur is S.CONFIRMED and states & {"PREPARING", "READY"}:
            self.orders.update_status(order_id, S.PREPARING)
            cur = S.PREPARING
        if cur is S.PREPARING and states == {"READY"}:
            self.orders.update_status(order_id, S.READY)

    def mark_sold_out(self, menu_item_id: int) -> None:
        self.menu.set_availability(menu_item_id, False)
