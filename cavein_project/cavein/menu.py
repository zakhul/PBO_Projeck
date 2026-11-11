"""Modul Menu — Farhat Bima Raditya. FR-02, FR-03, FR-18, FR-19."""
from __future__ import annotations

import sqlite3

from .core import CaveinError


class MenuService:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    # ---- CRUD (admin) ----
    def add_category(self, name: str, display_order: int = 0) -> int:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO category(name, display_order) VALUES (?, ?)", (name, display_order))
        return cur.lastrowid

    def add_item(self, category_id: int, name: str, price: int, description: str = "",
                 image_url: str = "", vegetarian: bool = False) -> int:
        if price < 0:
            raise CaveinError("Harga tidak boleh negatif")
        with self.db:
            cur = self.db.execute(
                "INSERT INTO menu_item(category_id, name, description, image_url, price, is_vegetarian)"
                " VALUES (?,?,?,?,?,?)",
                (category_id, name, description, image_url, price, int(vegetarian)))
        return cur.lastrowid

    def add_option(self, item_id: int, name: str, choices: list[tuple[str, int]],
                   required: bool = False) -> int:
        """choices: [(label, extra_price), ...]; contoh: ('Level pedas', [('Sedang', 0), ('Pedas', 2000)])"""
        if not choices:
            raise CaveinError("Opsi harus punya minimal satu pilihan")
        with self.db:
            cur = self.db.execute(
                "INSERT INTO menu_option(menu_item_id, name, is_required) VALUES (?,?,?)",
                (item_id, name, int(required)))
            oid = cur.lastrowid
            self.db.executemany(
                "INSERT INTO option_choice(menu_option_id, label, extra_price) VALUES (?,?,?)",
                [(oid, label, extra) for label, extra in choices])
        return oid

    def update_price(self, item_id: int, price: int) -> None:
        if price < 0:
            raise CaveinError("Harga tidak boleh negatif")
        self._update(item_id, "price", price)

    def set_availability(self, item_id: int, available: bool) -> None:
        self._update(item_id, "is_available", int(available))

    def _update(self, item_id: int, column: str, value) -> None:
        with self.db:
            cur = self.db.execute(f"UPDATE menu_item SET {column}=? WHERE id=?", (value, item_id))
        if cur.rowcount == 0:
            raise CaveinError("Menu tidak ditemukan")

    # ---- baca (pelanggan) ----
    def is_orderable(self, item_id: int) -> bool:
        row = self.db.execute("SELECT is_available FROM menu_item WHERE id=?", (item_id,)).fetchone()
        return bool(row and row["is_available"])

    def list_menu(self, category_id: int | None = None, keyword: str | None = None,
                  max_price: int | None = None, vegetarian: bool | None = None) -> list[sqlite3.Row]:
        sql = ("SELECT m.id, c.name AS category, m.name, m.description, m.price, m.image_url,"
               " m.is_available, m.is_vegetarian"
               " FROM menu_item m JOIN category c ON c.id = m.category_id WHERE 1=1")
        args: list = []
        if category_id is not None:
            sql += " AND m.category_id=?"
            args.append(category_id)
        if keyword:
            sql += " AND m.name LIKE ?"
            args.append(f"%{keyword}%")
        if max_price is not None:
            sql += " AND m.price<=?"
            args.append(max_price)
        if vegetarian:
            sql += " AND m.is_vegetarian=1"
        sql += " ORDER BY c.display_order, m.name"
        return self.db.execute(sql, args).fetchall()

    def options_of(self, item_id: int) -> list[dict]:
        rows = self.db.execute(
            "SELECT mo.id AS option_id, mo.name AS option_name, mo.is_required,"
            " oc.id AS choice_id, oc.label, oc.extra_price"
            " FROM menu_option mo JOIN option_choice oc ON oc.menu_option_id = mo.id"
            " WHERE mo.menu_item_id=? ORDER BY mo.id, oc.id", (item_id,)).fetchall()
        out: dict[int, dict] = {}
        for r in rows:
            opt = out.setdefault(r["option_id"], {
                "id": r["option_id"], "name": r["option_name"],
                "required": bool(r["is_required"]), "choices": []})
            opt["choices"].append({"id": r["choice_id"], "label": r["label"], "extra": r["extra_price"]})
        return list(out.values())
