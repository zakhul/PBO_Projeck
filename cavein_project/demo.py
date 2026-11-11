"""Demo alur lengkap: scan QR -> pesan -> dapur -> bayar -> tutup sesi -> laporan."""
from cavein import Cart, create_app
from cavein.core import OrderStatus as S, rupiah

app = create_app()
app.notifier.subscribe("kitchen", lambda p: print(f"  [DAPUR]  pesanan baru {p['order_number']}"))
app.notifier.subscribe("cashier", lambda p: print(f"  [KASIR]  {p['order_number']} -> {p['status']}"))

# --- admin menyiapkan data ---
m = app.menu
minuman, makanan = m.add_category("Minuman", 1), m.add_category("Makanan", 2)
kopi = m.add_item(minuman, "Kopi Susu", 20000)
m.add_option(kopi, "Gula", [("Normal", 0), ("Less", 0)], required=True)
m.add_option(kopi, "Topping", [("Extra shot", 5000)])
nasgor = m.add_item(makanan, "Nasi Goreng", 30000, vegetarian=False)
salad = m.add_item(makanan, "Salad", 25000, vegetarian=True)
app.vouchers.create("HEMAT10", "PERCENT", 10, min_purchase=50000, quota=5)
kasir = app.auth.create_staff("Rina", "rina", "rahasia1", "CASHIER")
t1 = app.tables.add_table(1)

# --- pelanggan scan QR & pesan ---
qr = app.tables.qr_payload(t1)
_, sesi = app.tables.scan(qr)
gula, extra = (c["id"] for opt in m.options_of(kopi) for c in opt["choices"] if c["label"] in ("Less", "Extra shot"))
cart = Cart(sesi)
cart.add_item(kopi, 2, [gula, extra], note="es dipisah")
cart.add_item(nasgor, 1)
print("Subtotal keranjang:", rupiah(app.orders.price_cart(cart)))
oid = app.orders.checkout(cart)

# --- kasir konfirmasi + voucher ---
app.auth.require("CASHIER", "order.confirm")
app.orders.confirm(oid, kasir)
print("Diskon voucher:", rupiah(app.vouchers.apply(oid, "hemat10")))

# --- dapur ---
for pesanan in app.kitchen.queue():
    print(f"  [LAYAR DAPUR] meja {pesanan['table_number']} {pesanan['order_number']}")
    for it in pesanan["items"]:
        print(f"      {it['quantity']}x {it['name']} {it['options'] or ''} {it['note'] or ''}")
        app.kitchen.set_item_status(it["id"], S.PREPARING)
        app.kitchen.set_item_status(it["id"], S.READY)

# --- sajikan, bayar, tutup sesi ---
app.orders.serve(oid)
app.payments.pay(oid, "QRIS", ref="TRX-001")
print(app.payments.receipt(oid))
app.tables.close_session(sesi)
app.orders.add_review(oid, 5, "Enak!")

# --- laporan admin ---
print("Penjualan harian :", [tuple(r) for r in app.reports.sales("day")])
print("Menu terlaris    :", [tuple(r) for r in app.reports.top_items()])
print("Per metode bayar :", [tuple(r) for r in app.reports.revenue_by_method()])
