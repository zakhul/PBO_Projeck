import unittest

from cavein import Cart, create_app
from cavein.core import CaveinError, OrderStatus as S, PermissionDenied, compute_totals


class CaveinTest(unittest.TestCase):
    def setUp(self):
        a = self.app = create_app()
        cat = a.menu.add_category("Menu")
        self.kopi = a.menu.add_item(cat, "Kopi", 20000)
        self.opt = a.menu.add_option(self.kopi, "Gula", [("Normal", 0), ("Less", 0)], required=True)
        self.normal = a.menu.options_of(self.kopi)[0]["choices"][0]["id"]
        self.nasi = a.menu.add_item(cat, "Nasi", 30000)
        self.t = a.tables.add_table(1)
        _, self.sesi = a.tables.scan(a.tables.qr_payload(self.t))

    def order(self, *items):
        c = Cart(self.sesi)
        for i, q, ch in items:
            c.add_item(i, q, ch)
        return self.app.orders.checkout(c)

    def test_totals_pajak_dan_service(self):
        self.assertEqual(compute_totals(80000), (8800, 4000, 92800))

    def test_opsi_wajib(self):
        with self.assertRaises(CaveinError):
            self.order((self.kopi, 1, ()))

    def test_menu_habis_tidak_bisa_dipesan(self):
        self.app.kitchen.mark_sold_out(self.nasi)
        with self.assertRaises(CaveinError):
            self.order((self.nasi, 1, ()))

    def test_satu_sesi_aktif_per_meja(self):
        _, s2 = self.app.tables.scan(self.app.tables.qr_payload(self.t))
        self.assertEqual(self.sesi, s2)

    def test_snapshot_harga(self):
        oid = self.order((self.nasi, 1, ()))
        self.app.menu.update_price(self.nasi, 99999)
        self.assertEqual(self.app.orders.get(oid)["subtotal"], 30000)

    def test_pelanggan_tidak_bisa_batal_saat_diproses(self):
        o = self.app.orders
        oid = self.order((self.nasi, 1, ()))
        o.confirm(oid)
        o.cancel(oid, "ganti menu", by_customer=True)  # CONFIRMED masih boleh
        oid2 = self.order((self.nasi, 1, ()))
        o.confirm(oid2)
        item = self.app.kitchen.queue()[0]["items"][0]["id"]
        self.app.kitchen.set_item_status(item, S.PREPARING)
        with self.assertRaises(CaveinError):
            o.cancel(oid2, "x", by_customer=True)
        o.cancel(oid2, "bahan habis")  # staf boleh

    def test_alur_penuh_dan_tutup_sesi(self):
        a = self.app
        oid = self.order((self.kopi, 2, (self.normal,)))
        with self.assertRaises(CaveinError):
            a.tables.close_session(self.sesi)  # masih ada pesanan aktif
        a.orders.confirm(oid)
        for it in a.kitchen.queue()[0]["items"]:
            a.kitchen.set_item_status(it["id"], S.PREPARING)
            a.kitchen.set_item_status(it["id"], S.READY)
        self.assertEqual(a.orders.get(oid)["status"], "READY")
        a.orders.serve(oid)
        self.assertEqual(a.orders.get(oid)["status"], "SERVED")  # belum dibayar
        a.payments.pay(oid, "CASH")
        self.assertEqual(a.orders.get(oid)["status"], "COMPLETED")
        a.tables.close_session(self.sesi)
        a.orders.add_review(oid, 4)
        with self.assertRaises(CaveinError):
            a.orders.add_review(oid, 5)  # satu ulasan per pesanan
        self.assertEqual(a.reports.revenue_by_method()[0]["revenue"], a.orders.get(oid)["total_amount"])

    def test_pembayaran_gagal_lalu_ulang(self):
        a = self.app
        a.payments.gateway = lambda *x: False
        oid = self.order((self.nasi, 1, ()))
        self.assertEqual(a.payments.pay(oid, "QRIS").value, "FAILED")
        a.payments.gateway = lambda *x: True
        self.assertEqual(a.payments.pay(oid, "QRIS").value, "PAID")

    def test_voucher(self):
        a = self.app
        oid = self.order((self.nasi, 2, ()))  # subtotal 60000
        a.vouchers.create("PROMO", "FIXED", 5000, min_purchase=100000)
        with self.assertRaises(CaveinError):
            a.vouchers.apply(oid, "PROMO")  # belum memenuhi minimal
        a.vouchers.create("DISK", "PERCENT", 10, quota=1)
        self.assertEqual(a.vouchers.apply(oid, "disk"), 6000)
        oid2 = self.order((self.nasi, 1, ()))
        with self.assertRaises(CaveinError):
            a.vouchers.apply(oid2, "DISK")  # kuota habis

    def test_auth(self):
        a = self.app
        a.auth.create_staff("Rina", "rina", "rahasia1", "CASHIER")
        self.assertIsNotNone(a.auth.login("rina", "rahasia1"))
        self.assertIsNone(a.auth.login("rina", "salah"))
        with self.assertRaises(PermissionDenied):
            a.auth.require("KITCHEN", "payment.process")


if __name__ == "__main__":
    unittest.main(verbosity=1)
