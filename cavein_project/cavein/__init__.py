"""Cavein: backend E-Menu kafe/restoran. Python murni (stdlib) + SQLite."""
from types import SimpleNamespace

from .billing import PaymentService, ReportService, VoucherService
from .core import Notifier, connect
from .floor import AuthService, KitchenDisplayService, TableService
from .menu import MenuService
from .orders import Cart, OrderService

__all__ = ["create_app", "Cart"]


def create_app(path: str = ":memory:") -> SimpleNamespace:
    """Rakit semua service. path=':memory:' untuk uji; isi nama file untuk menyimpan permanen."""
    db, notifier = connect(path), Notifier()
    menu, orders = MenuService(db), OrderService(db, notifier)
    return SimpleNamespace(
        db=db, notifier=notifier, menu=menu, orders=orders,
        vouchers=VoucherService(db), payments=PaymentService(db, orders), reports=ReportService(db),
        tables=TableService(db), auth=AuthService(db), kitchen=KitchenDisplayService(db, orders, menu))
