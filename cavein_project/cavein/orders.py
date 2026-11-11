"""Modul Pesanan — Zaki Rahul Fawas. FR-04, FR-05, FR-07, FR-08, FR-09, FR-10, FR-11, FR-13."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from .core import CaveinError, Notifier, OrderStatus as S, compute_totals, now

# Alur status yang sah. COMPLETED hanya tercapai setelah dibayar DAN disajikan.
FLOW = {
    S.PENDING: {S.CONFIRMED, S.CANCELLED},
    S.CONFIRMED: {S.PREPARING, S.CANCELLED},
    S.PREPARING: {S.READY, S.CANCELLED},
    S.READY: {S.SERVED, S.CANCELLED},
    S.SERVED: {S.COMPLETED},
    S.COMPLETED: set(),
    S.CANCELLED: set(),
}
# Aturan bisnis: pesanan "Diproses" (PREPARING) tidak bisa dibatalkan pelanggan.
CUSTOMER_CANCELLABLE = {S.PENDING, S.CONFIRMED}


@dataclass
class CartItem:
    menu_item_id: int
    quantity: int = 1
    choice_ids: tuple = ()
    note: str = ""


@dataclass
class Cart:
    """Keranjang hidup di sisi klien/memori; baru jadi ORDERS saat checkout."""
    session_id: int
    items: list[CartItem] = field(default_factory=list)

    def add_item(self, menu_item_id: int, qty: int = 1, choice_ids=(), note: str = "") -> int:
        if qty < 1:
            raise CaveinError("Jumlah minimal 1")
        self.items.append(CartItem(menu_item_id, qty, tuple(choice_ids), note))
        return len(self.items) - 1

    def remove_item(self, index: int) -> None:
        del self.items[index]

    def update_quantity(self, index: int, qty: int) -> None:
        if qty <= 0:
            self.remove_item(index)
        else:
            self.items[index].quantity = qty

    def clear(self) -> None:
        self.items.clear()


class OrderService:
    def __init__(self, db: sqlite3.Connection, notifier: Notifier) -> None:
        self.db = db
        self.notifier = notifier

    # ---- baca ----
    def get(self, order_id: int) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if row is None:
            raise CaveinError("Pesanan tidak ditemukan")
        return row

    def orders_of_session(self, session_id: int) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM orders WHERE session_id=? ORDER BY id", (session_id,)).fetchall()

    # ---- checkout ----
    def _price_line(self, ci: CartItem):
        """Validasi satu baris keranjang; return (menu_row, [(choice_id, extra_price)])."""
        item = self.db.execute(
            "SELECT id, name, price, is_available FROM menu_item WHERE id=?",
            (ci.menu_item_id,)).fetchone()
        if item is None:
            raise CaveinError("Menu tidak ditemukan")
        if not item["is_available"]:
            raise CaveinError(f"Menu '{item['name']}' habis")  # aturan bisnis: menu habis tidak bisa dipesan

        valid = {r["id"]: r for r in self.db.execute(
            "SELECT oc.id, oc.extra_price, oc.menu_option_id FROM option_choice oc"
            " JOIN menu_option mo ON mo.id = oc.menu_option_id WHERE mo.menu_item_id=?",
            (item["id"],))}
        chosen = list(ci.choice_ids)
        if not set(chosen) <= valid.keys():
            raise CaveinError(f"Ada pilihan yang tidak sesuai untuk '{item['name']}'")
        picked = {valid[c]["menu_option_id"] for c in chosen}
        if len(picked) != len(chosen):
            raise CaveinError("Hanya boleh satu pilihan per opsi")
        required = {r["id"] for r in self.db.execute(
            "SELECT id FROM menu_option WHERE menu_item_id=? AND is_required=1", (item["id"],))}
        if not required <= picked:
            raise CaveinError(f"Opsi wajib untuk '{item['name']}' belum dipilih")
        return item, [(c, valid[c]["extra_price"]) for c in chosen]

    def price_cart(self, cart: Cart) -> int:
        """Subtotal keranjang (sekaligus memvalidasi isinya)."""
        return sum((it["price"] + sum(e for _, e in extras)) * ci.quantity
                   for ci in cart.items for it, extras in [self._price_line(ci)])

    def checkout(self, cart: Cart, customer_id: int | None = None) -> int:
        if not cart.items:
            raise CaveinError("Keranjang kosong")
        sess = self.db.execute(
            "SELECT status FROM table_session WHERE id=?", (cart.session_id,)).fetchone()
        if sess is None or sess["status"] != "OPEN":
            raise CaveinError("Sesi meja tidak aktif")

        lines = [(ci, *self._price_line(ci)) for ci in cart.items]
        subtotal = sum((it["price"] + sum(e for _, e in extras)) * ci.quantity
                       for ci, it, extras in lines)
        tax, service, total = compute_totals(subtotal)

        with self.db:
            cur = self.db.execute(
                "INSERT INTO orders(session_id, customer_id, status, subtotal, tax,"
                " service_charge, discount, total_amount, created_at) VALUES (?,?,?,?,?,?,0,?,?)",
                (cart.session_id, customer_id, S.PENDING.value, subtotal, tax, service, total, now()))
            oid = cur.lastrowid
            number = f"ORD-{now()[:10].replace('-', '')}-{oid:05d}"
            self.db.execute("UPDATE orders SET order_number=? WHERE id=?", (number, oid))
            for ci, it, extras in lines:
                oi = self.db.execute(
                    "INSERT INTO order_item(order_id, menu_item_id, quantity, unit_price, note, status)"
                    " VALUES (?,?,?,?,?,?)",
                    (oid, it["id"], ci.quantity, it["price"], ci.note, S.PENDING.value)).lastrowid
                self.db.executemany(
                    "INSERT INTO order_item_choice(order_item_id, option_choice_id, extra_price) VALUES (?,?,?)",
                    [(oi, cid, extra) for cid, extra in extras])
        cart.clear()
        self._notify(oid, number, S.PENDING)
        return oid

    # ---- status ----
    def update_status(self, order_id: int, new: S) -> None:
        o = self.get(order_id)
        cur, new = S(o["status"]), S(new)
        if new not in FLOW[cur]:
            raise CaveinError(f"Transisi {cur} -> {new} tidak diizinkan")
        if new is S.COMPLETED and not self._is_paid(order_id):
            raise CaveinError("Pesanan belum dibayar")
        with self.db:
            self.db.execute("UPDATE orders SET status=? WHERE id=?", (new.value, order_id))
            if new in (S.CONFIRMED, S.SERVED):
                self.db.execute(
                    "UPDATE order_item SET status=? WHERE order_id=? AND status!='CANCELLED'",
                    (new.value, order_id))
            elif new is S.CANCELLED:
                self.db.execute("UPDATE order_item SET status='CANCELLED' WHERE order_id=?", (order_id,))
        self._notify(order_id, o["order_number"], new)
        if new is S.SERVED:
            self.try_complete(order_id)

    def confirm(self, order_id: int, staff_id: int | None = None) -> None:
        with self.db:
            self.db.execute("UPDATE orders SET confirmed_by=? WHERE id=?", (staff_id, order_id))
        self.update_status(order_id, S.CONFIRMED)

    def serve(self, order_id: int) -> None:
        self.update_status(order_id, S.SERVED)

    def cancel(self, order_id: int, reason: str, by_customer: bool = False) -> None:
        if not reason or not reason.strip():
            raise CaveinError("Alasan pembatalan wajib diisi")
        o = self.get(order_id)
        if by_customer and S(o["status"]) not in CUSTOMER_CANCELLABLE:
            raise CaveinError("Pesanan sudah diproses dan tidak bisa dibatalkan pelanggan")
        if self._is_paid(order_id):
            raise CaveinError("Pesanan sudah dibayar; lakukan refund terlebih dahulu")
        with self.db:
            self.db.execute("UPDATE orders SET cancel_reason=? WHERE id=?", (reason.strip(), order_id))
        self.update_status(order_id, S.CANCELLED)

    def try_complete(self, order_id: int) -> None:
        """Selesai = sudah dibayar DAN sudah disajikan."""
        if self.get(order_id)["status"] == S.SERVED.value and self._is_paid(order_id):
            self.update_status(order_id, S.COMPLETED)

    def _is_paid(self, order_id: int) -> bool:
        return self.db.execute(
            "SELECT 1 FROM payment WHERE order_id=? AND status='PAID'", (order_id,)).fetchone() is not None

    def _notify(self, order_id: int, number: str, status: S) -> None:
        payload = {"order_id": order_id, "order_number": number, "status": status.value}
        self.notifier.publish(f"order:{order_id}", payload)   # pelanggan memantau status
        if status is S.PENDING:
            self.notifier.publish("cashier", payload)          # pesanan baru masuk kasir
        elif status is S.CONFIRMED:
            self.notifier.publish("kitchen", payload)          # lanjut ke layar dapur
        elif status is S.READY:
            self.notifier.publish("cashier", payload)          # siap disajikan

    # ---- ulasan ----
    def add_review(self, order_id: int, rating: int, comment: str = "") -> None:
        if not 1 <= rating <= 5:
            raise CaveinError("Rating harus 1-5")
        if self.get(order_id)["status"] != S.COMPLETED.value:
            raise CaveinError("Ulasan hanya untuk pesanan yang sudah selesai")
        try:
            with self.db:
                self.db.execute(
                    "INSERT INTO review(order_id, rating, comment, created_at) VALUES (?,?,?,?)",
                    (order_id, rating, comment, now()))
        except sqlite3.IntegrityError:
            raise CaveinError("Pesanan ini sudah diulas") from None
