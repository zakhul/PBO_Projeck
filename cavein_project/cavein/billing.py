"""Modul Pembayaran, Promo, dan Laporan — Putra Agung Srihandaka. FR-06, FR-12, FR-14, FR-22, FR-23."""
from __future__ import annotations

import sqlite3
from typing import Callable

from .core import (TAX_RATE_PCT, CaveinError, OrderStatus as S, PaymentMethod,
                   PaymentStatus, compute_totals, now, rupiah)
from .orders import OrderService


class VoucherService:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def create(self, code: str, discount_type: str, value: int, min_purchase: int = 0,
               valid_from: str | None = None, valid_until: str | None = None, quota: int = 1) -> int:
        """discount_type: 'PERCENT' (value 1-100) atau 'FIXED' (rupiah). Tanggal format ISO."""
        if discount_type == "PERCENT" and not 1 <= value <= 100:
            raise CaveinError("Persentase diskon harus 1-100")
        if value <= 0:
            raise CaveinError("Nilai diskon harus positif")
        try:
            with self.db:
                cur = self.db.execute(
                    "INSERT INTO voucher(code, discount_type, value, min_purchase, valid_from,"
                    " valid_until, quota) VALUES (?,?,?,?,?,?,?)",
                    (code.upper(), discount_type, value, min_purchase, valid_from, valid_until, quota))
        except sqlite3.IntegrityError as e:
            raise CaveinError(f"Voucher tidak valid atau kode sudah ada: {e}") from None
        return cur.lastrowid

    @staticmethod
    def calculate_discount(v: sqlite3.Row, subtotal: int) -> int:
        disc = subtotal * v["value"] // 100 if v["discount_type"] == "PERCENT" else v["value"]
        return min(disc, subtotal)

    def apply(self, order_id: int, code: str) -> int:
        """Terapkan voucher ke pesanan; return nilai diskon."""
        o = self.db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if o is None:
            raise CaveinError("Pesanan tidak ditemukan")
        if o["status"] in (S.CANCELLED.value, S.COMPLETED.value):
            raise CaveinError("Voucher tidak bisa diterapkan pada pesanan ini")
        if o["voucher_id"]:
            raise CaveinError("Pesanan sudah memakai voucher")
        if self.db.execute("SELECT 1 FROM payment WHERE order_id=? AND status='PAID'", (order_id,)).fetchone():
            raise CaveinError("Pesanan sudah dibayar")

        v = self.db.execute("SELECT * FROM voucher WHERE code=?", (code.upper(),)).fetchone()
        if v is None:
            raise CaveinError("Kode voucher tidak ditemukan")
        t = now()
        if (v["valid_from"] and t < v["valid_from"]) or (v["valid_until"] and t > v["valid_until"]):
            raise CaveinError("Voucher di luar masa berlaku")
        if o["subtotal"] < v["min_purchase"]:
            raise CaveinError(f"Minimal belanja {rupiah(v['min_purchase'])}")
        used = self.db.execute(
            "SELECT COUNT(*) FROM orders WHERE voucher_id=? AND status!='CANCELLED'", (v["id"],)).fetchone()[0]
        if used >= v["quota"]:
            raise CaveinError("Kuota voucher habis")

        disc = self.calculate_discount(v, o["subtotal"])
        _, _, total = compute_totals(o["subtotal"], disc)
        with self.db:
            self.db.execute(
                "UPDATE orders SET voucher_id=?, discount=?, total_amount=? WHERE id=?",
                (v["id"], disc, total, order_id))
        return disc


def _auto_gateway(method, amount, ref) -> bool:
    """Stub payment gateway. Ganti dengan integrasi QRIS/e-wallet/kartu resmi."""
    return True


class PaymentService:
    def __init__(self, db: sqlite3.Connection, orders: OrderService,
                 gateway: Callable[[PaymentMethod, int, str | None], bool] = _auto_gateway) -> None:
        self.db = db
        self.orders = orders
        self.gateway = gateway

    def pay(self, order_id: int, method: PaymentMethod | str, ref: str | None = None) -> PaymentStatus:
        o = self.orders.get(order_id)
        if o["status"] in (S.CANCELLED.value, S.COMPLETED.value):
            raise CaveinError("Pesanan tidak bisa dibayar")
        prev = self.db.execute("SELECT status FROM payment WHERE order_id=?", (order_id,)).fetchone()
        if prev and prev["status"] == PaymentStatus.PAID.value:
            raise CaveinError("Pesanan sudah dibayar")

        method = PaymentMethod(method)
        # Tunai dikonfirmasi langsung oleh kasir; metode lain diverifikasi gateway.
        ok = True if method is PaymentMethod.CASH else bool(self.gateway(method, o["total_amount"], ref))
        status = PaymentStatus.PAID if ok else PaymentStatus.FAILED
        with self.db:
            self.db.execute(
                "INSERT INTO payment(order_id, method, amount, status, paid_at, transaction_ref)"
                " VALUES (?,?,?,?,?,?) ON CONFLICT(order_id) DO UPDATE SET method=excluded.method,"
                " amount=excluded.amount, status=excluded.status, paid_at=excluded.paid_at,"
                " transaction_ref=excluded.transaction_ref",
                (order_id, method.value, o["total_amount"], status.value, now() if ok else None, ref))
        if ok:
            self.orders.try_complete(order_id)
        return status

    def refund(self, order_id: int) -> None:
        with self.db:
            cur = self.db.execute(
                "UPDATE payment SET status='REFUNDED' WHERE order_id=? AND status='PAID'", (order_id,))
        if cur.rowcount == 0:
            raise CaveinError("Tidak ada pembayaran lunas untuk di-refund")

    def receipt(self, order_id: int) -> str:
        o = self.orders.get(order_id)
        rows = self.db.execute(
            "SELECT mi.name, oi.quantity, oi.unit_price, oi.note,"
            " COALESCE((SELECT SUM(extra_price) FROM order_item_choice c WHERE c.order_item_id=oi.id),0) AS extra"
            " FROM order_item oi JOIN menu_item mi ON mi.id = oi.menu_item_id"
            " WHERE oi.order_id=? AND oi.status!='CANCELLED'", (order_id,)).fetchall()
        pay = self.db.execute("SELECT method, status FROM payment WHERE order_id=?", (order_id,)).fetchone()
        L = [f"STRUK {o['order_number']}", "-" * 34]
        for r in rows:
            L.append(f"{r['quantity']}x {r['name']:<18}{rupiah((r['unit_price'] + r['extra']) * r['quantity']):>12}")
        L += ["-" * 34,
              f"{'Subtotal':<20}{rupiah(o['subtotal']):>14}",
              f"{f'PPN {TAX_RATE_PCT}%':<20}{rupiah(o['tax']):>14}",
              f"{'Service':<20}{rupiah(o['service_charge']):>14}"]
        if o["discount"]:
            L.append(f"{'Diskon':<20}{'-' + rupiah(o['discount']):>14}")
        L.append(f"{'TOTAL':<20}{rupiah(o['total_amount']):>14}")
        L.append(f"Pembayaran: {pay['method']} ({pay['status']})" if pay else "Pembayaran: belum ada")
        return "\n".join(L)


class ReportService:
    """Semua laporan memakai agregasi SQL, jadi hemat memori."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def sales(self, period: str = "day", start: str = "0000", end: str = "9999") -> list[sqlite3.Row]:
        """Penjualan per 'day' atau 'month'. start/end: awalan tanggal ISO, mis. '2026-11'."""
        n = 10 if period == "day" else 7
        return self.db.execute(
            f"SELECT substr(paid_at,1,{n}) AS period, COUNT(*) AS orders, SUM(amount) AS revenue"
            " FROM payment WHERE status='PAID' AND paid_at >= ? AND paid_at <= ?"
            " GROUP BY period ORDER BY period", (start, end + "~")).fetchall()

    def top_items(self, limit: int = 5) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT mi.name, SUM(oi.quantity) AS qty FROM order_item oi"
            " JOIN menu_item mi ON mi.id = oi.menu_item_id"
            " JOIN payment p ON p.order_id = oi.order_id AND p.status='PAID'"
            " WHERE oi.status!='CANCELLED' GROUP BY mi.id ORDER BY qty DESC, mi.name LIMIT ?",
            (limit,)).fetchall()

    def revenue_by_method(self) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT method, COUNT(*) AS orders, SUM(amount) AS revenue FROM payment"
            " WHERE status='PAID' GROUP BY method ORDER BY revenue DESC").fetchall()
