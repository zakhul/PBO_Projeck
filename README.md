[README.md](https://github.com/user-attachments/files/34666918/README.md)
# PBO_Projeck
# 🍽️ Cavein: Sistem Pemesanan Menu Kafe / Restoran

## Latar Belakang dan Tujuan
 
Pemesanan di kafe dan restoran yang dilakukan secara manual membutuhkan waktu, bergantung pada ketersediaan pelayan, dan rawan salah catat antara meja, kasir, dan dapur. E-Menu dirancang sebagai sistem pemesanan digital berbasis QR code untuk mengatasi hal tersebut.
 
Tujuan proyek:
 
1. Merumuskan kebutuhan fungsional, kebutuhan non-fungsional, dan aturan bisnis sistem E-Menu.
2. Merancang class, use case, dan ERD yang menjadi dasar implementasi.
3. Memodelkan alur pemesanan dari pelanggan, kasir, dan dapur hingga laporan admin dengan pendekatan berorientasi objek.
4. Menyediakan kerangka kode awal sebagai titik mulai tahap implementasi.

## Daftar Isi

- [Aktor](#aktor)
- [Alur Singkat](#alur-singkat)
- [Kebutuhan Fungsional](#kebutuhan-fungsional)
- [Kebutuhan Non-Fungsional](#kebutuhan-non-fungsional)
- [Aturan Bisnis](#aturan-bisnis)
- [Desain Class](#desain-class)
- [Class Diagram](#class-diagram)
- [Use Case Diagram](#use-case-diagram)
- [ERD](#erd)
- [Contoh Kerangka Kode](#contoh-kerangka-kode)
- [Roadmap](#roadmap)
- [Kontribusi](#kontribusi)
- [Lisensi](#lisensi)

## Aktor

| Aktor | Peran |
|---|---|
| Pelanggan | Scan QR, melihat menu, memesan, membayar, memberi ulasan |
| Kasir | Mengonfirmasi pesanan, memproses pembayaran, menerapkan voucher, menutup sesi meja |
| Staf Dapur (Koki/Barista) | Mengelola antrean pesanan dan status item, menandai menu habis |
| Admin / Pemilik | Mengelola menu, meja, staf, promo, dan laporan |

## Alur Singkat

1. Pelanggan scan QR di meja, nomor meja terdeteksi otomatis.
2. Pelanggan memilih menu, mengatur kustomisasi (pedas, gula, topping), lalu checkout.
3. Pesanan masuk ke kasir dan layar dapur (kitchen display).
4. Dapur mengubah status: Diproses, lalu Siap. Pelanggan memantau status secara real-time.
5. Pesanan disajikan, dibayar, lalu sesi meja ditutup oleh kasir.

## Kebutuhan Fungsional

<details>
<summary><b>Pelanggan (FR-01 s.d. FR-10)</b></summary>

| ID | Kebutuhan |
|---|---|
| FR-01 | Mengakses menu dengan scan QR code meja (nomor meja terdeteksi otomatis) |
| FR-02 | Melihat menu per kategori (makanan, minuman, dessert) lengkap dengan foto, harga, deskripsi, dan status ketersediaan |
| FR-03 | Mencari dan memfilter menu (kategori, harga, vegetarian, dll.) |
| FR-04 | Mengelola keranjang, termasuk opsi kustomisasi dan catatan |
| FR-05 | Membuat pesanan dari keranjang |
| FR-06 | Memilih metode pembayaran (tunai di kasir, QRIS, e-wallet, kartu) |
| FR-07 | Memantau status pesanan (Diterima, Diproses, Siap, Disajikan) |
| FR-08 | Menambah pesanan susulan di meja yang sama |
| FR-09 | Melihat riwayat dan struk pesanan |
| FR-10 | Memberi rating dan ulasan |

</details>

<details>
<summary><b>Kasir (FR-11 s.d. FR-15)</b></summary>

| ID | Kebutuhan |
|---|---|
| FR-11 | Melihat dan mengonfirmasi pesanan masuk |
| FR-12 | Memproses pembayaran dan mencetak/mengirim struk |
| FR-13 | Membatalkan atau mengubah pesanan (dengan alasan) |
| FR-14 | Menerapkan diskon/voucher |
| FR-15 | Menutup sesi meja setelah pembayaran |

</details>

<details>
<summary><b>Dapur (FR-16 s.d. FR-18)</b></summary>

| ID | Kebutuhan |
|---|---|
| FR-16 | Melihat antrean pesanan berurutan (kitchen display) |
| FR-17 | Mengubah status item/pesanan (Diproses, Siap) |
| FR-18 | Menandai menu habis (stok kosong) |

</details>

<details>
<summary><b>Admin (FR-19 s.d. FR-24)</b></summary>

| ID | Kebutuhan |
|---|---|
| FR-19 | CRUD menu, kategori, harga, foto, dan opsi tambahan |
| FR-20 | Mengelola meja dan generate QR code per meja |
| FR-21 | Mengelola akun staf dan hak akses (role) |
| FR-22 | Mengelola promo, diskon, dan voucher |
| FR-23 | Laporan penjualan harian/bulanan, menu terlaris, dan pendapatan per metode bayar |
| FR-24 | Mengelola stok bahan/menu (opsional) |

</details>

## Kebutuhan Non-Fungsional

| Aspek | Kebutuhan |
|---|---|
| Performa | Halaman menu dimuat < 3 detik; mendukung minimal 100 pengguna bersamaan |
| Real-time | Status pesanan dan antrean dapur diperbarui otomatis (WebSocket/polling) |
| Keamanan | Hash password, role-based access, payment gateway resmi, perlindungan data pelanggan |
| Usability | Mobile-first, tanpa instal aplikasi, mudah dipakai tanpa pelatihan |
| Ketersediaan | Uptime ≥ 99%; pesanan tidak hilang saat koneksi terputus sesaat |
| Skalabilitas | Mendukung penambahan cabang/outlet |
| Maintainability | Arsitektur modular dan backup data harian |

## Aturan Bisnis

- Satu meja hanya punya satu sesi aktif; semua pesanan di meja itu masuk ke satu tagihan.
- Menu berstatus "habis" tidak bisa dipesan.
- Pesanan berstatus "Diproses" tidak bisa dibatalkan pelanggan.
- Pajak (PPN) dan service charge dihitung otomatis dari subtotal.
- Pesanan dianggap selesai setelah dibayar dan disajikan.

## Desain Class

**Enum**

| Enum | Nilai |
|---|---|
| `OrderStatus` | PENDING, CONFIRMED, PREPARING, READY, SERVED, COMPLETED, CANCELLED |
| `PaymentStatus` | UNPAID, PAID, FAILED, REFUNDED |
| `PaymentMethod` | CASH, QRIS, EWALLET, CARD |
| `TableStatus` | AVAILABLE, OCCUPIED, RESERVED |
| `Role` | ADMIN, CASHIER, KITCHEN |

**Class layanan (service)**

| Class | Tanggung jawab |
|---|---|
| `MenuService` | CRUD menu, kategori, ketersediaan, pencarian |
| `OrderService` | Membuat pesanan, mengubah status, membatalkan, menghitung total |
| `PaymentService` | Integrasi payment gateway, verifikasi, refund |
| `TableService` | Manajemen meja, sesi, generate QR |
| `KitchenDisplayService` | Antrean dapur, update status item |
| `NotificationService` | Push status pesanan ke pelanggan, kasir, dan dapur |
| `ReportService` | Laporan penjualan dan menu terlaris |
| `AuthService` | Autentikasi dan otorisasi staf |

## Class Diagram

```mermaid
classDiagram
    direction LR
    class Category {
        +int id
        +String name
        +int displayOrder
        +getMenuItems()
    }
    class MenuItem {
        +int id
        +String name
        +String description
        +decimal price
        +String imageUrl
        +bool isAvailable
        +setAvailability(bool)
        +updatePrice(price)
        +isOrderable() bool
    }
    class MenuOption {
        +int id
        +String name
        +bool isRequired
    }
    class OptionChoice {
        +int id
        +String label
        +decimal extraPrice
    }
    class Table {
        +int id
        +int number
        +int capacity
        +String qrCode
        +TableStatus status
        +generateQRCode()
        +openSession()
        +closeSession()
    }
    class Customer {
        +int id
        +String name
        +String phone
        +String email
        +placeOrder()
        +viewOrderHistory()
    }
    class Cart {
        +int id
        +getSubtotal() decimal
        +addItem(menuItem, qty, options, note)
        +removeItem(id)
        +updateQuantity(id, qty)
        +clear()
    }
    class CartItem {
        +int id
        +int quantity
        +String note
        +getTotalPrice() decimal
    }
    class Order {
        +int id
        +String orderNumber
        +OrderStatus status
        +decimal subtotal
        +decimal tax
        +decimal serviceCharge
        +decimal discount
        +decimal totalAmount
        +datetime createdAt
        +calculateTotal()
        +updateStatus(status)
        +cancel(reason)
        +addItem(item)
        +applyVoucher(voucher)
    }
    class OrderItem {
        +int id
        +int quantity
        +decimal unitPrice
        +String note
        +OrderStatus status
        +getSubtotal() decimal
        +updateStatus(status)
    }
    class Payment {
        +int id
        +PaymentMethod method
        +decimal amount
        +PaymentStatus status
        +datetime paidAt
        +String transactionRef
        +process()
        +verify()
        +refund()
        +generateReceipt()
    }
    class Voucher {
        +int id
        +String code
        +String discountType
        +decimal value
        +decimal minPurchase
        +datetime validFrom
        +datetime validUntil
        +int quota
        +isValid(order) bool
        +calculateDiscount(subtotal) decimal
    }
    class Staff {
        +int id
        +String name
        +String username
        +String passwordHash
        +Role role
        +bool isActive
        +login()
        +logout()
        +hasPermission(action) bool
    }
    class Review {
        +int id
        +int rating
        +String comment
        +datetime createdAt
    }
    class OrderStatus {
        <<enumeration>>
        PENDING
        CONFIRMED
        PREPARING
        READY
        SERVED
        COMPLETED
        CANCELLED
    }
    class PaymentStatus {
        <<enumeration>>
        UNPAID
        PAID
        FAILED
        REFUNDED
    }
    class PaymentMethod {
        <<enumeration>>
        CASH
        QRIS
        EWALLET
        CARD
    }
    class TableStatus {
        <<enumeration>>
        AVAILABLE
        OCCUPIED
        RESERVED
    }
    class Role {
        <<enumeration>>
        ADMIN
        CASHIER
        KITCHEN
    }
    Category "1" --> "*" MenuItem
    MenuItem "1" --> "*" MenuOption
    MenuOption "1" --> "*" OptionChoice
    Table "1" --> "*" Order
    Customer "0..1" --> "*" Order
    Order "1" *-- "*" OrderItem
    OrderItem "*" --> "1" MenuItem
    OrderItem "*" --> "*" OptionChoice : selectedChoices
    Order "1" -- "1" Payment
    Order "*" --> "0..1" Voucher
    Order "1" -- "0..1" Review
    Cart "1" *-- "*" CartItem
    Cart "*" --> "1" Table
    CartItem "*" --> "1" MenuItem
    Cart ..> Order : checkout
    Order --> OrderStatus
    OrderItem --> OrderStatus
    Payment --> PaymentStatus
    Payment --> PaymentMethod
    Table --> TableStatus
    Staff --> Role
```

## Use Case Diagram

```mermaid
flowchart LR
    P([Pelanggan])
    K([Kasir])
    D([Staf Dapur])
    A([Admin])
    subgraph SYS[Sistem E-Menu]
        direction TB
        U01(Scan QR meja)
        U02(Lihat menu per kategori)
        U03(Cari dan filter menu)
        U04(Kelola keranjang)
        U05(Kustomisasi item dan catatan)
        U06(Buat pesanan)
        U07(Pilih metode pembayaran)
        U08(Pantau status pesanan)
        U09(Tambah pesanan susulan)
        U10(Lihat riwayat dan struk)
        U11(Beri rating dan ulasan)
        U12(Konfirmasi pesanan masuk)
        U13(Proses pembayaran dan cetak struk)
        U14(Batalkan atau ubah pesanan)
        U15(Terapkan diskon atau voucher)
        U16(Tutup sesi meja)
        U17(Lihat antrean dapur)
        U18(Ubah status item pesanan)
        U19(Tandai menu habis)
        U20(Kelola menu dan kategori)
        U21(Kelola meja dan QR code)
        U22(Kelola akun staf dan role)
        U23(Kelola promo dan voucher)
        U24(Lihat laporan penjualan)
        U25(Kelola stok)
        U26(Login staf)
    end
    P --- U01
    P --- U02
    P --- U03
    P --- U04
    P --- U06
    P --- U07
    P --- U08
    P --- U09
    P --- U10
    P --- U11
    K --- U12
    K --- U13
    K --- U14
    K --- U15
    K --- U16
    D --- U17
    D --- U18
    D --- U19
    A --- U20
    A --- U21
    A --- U22
    A --- U23
    A --- U24
    A --- U25
    U04 -.->|include| U05
    U06 -.->|include| U07
    U09 -.->|extend| U06
    U12 -.->|include| U26
    U17 -.->|include| U26
    U20 -.->|include| U26
```

## ERD

```mermaid
erDiagram
    OUTLET ||--o{ DINING_TABLE : memiliki
    OUTLET ||--o{ STAFF : mempekerjakan
    CATEGORY ||--o{ MENU_ITEM : memiliki
    MENU_ITEM ||--o{ MENU_OPTION : punya
    MENU_OPTION ||--o{ OPTION_CHOICE : berisi
    DINING_TABLE ||--o{ TABLE_SESSION : dibuka
    TABLE_SESSION ||--o{ ORDERS : berisi
    CUSTOMER |o--o{ ORDERS : membuat
    VOUCHER |o--o{ ORDERS : dipakai
    STAFF |o--o{ ORDERS : mengonfirmasi
    ORDERS ||--|{ ORDER_ITEM : terdiri_dari
    MENU_ITEM ||--o{ ORDER_ITEM : dipesan
    ORDER_ITEM ||--o{ ORDER_ITEM_CHOICE : memilih
    OPTION_CHOICE ||--o{ ORDER_ITEM_CHOICE : dipilih
    ORDERS ||--o| PAYMENT : dibayar
    ORDERS ||--o| REVIEW : dinilai
    OUTLET {
        int id PK
        string name
        string address
    }
    CATEGORY {
        int id PK
        string name
        int display_order
    }
    MENU_ITEM {
        int id PK
        int category_id FK
        string name
        text description
        decimal price
        string image_url
        boolean is_available
    }
    MENU_OPTION {
        int id PK
        int menu_item_id FK
        string name
        boolean is_required
    }
    OPTION_CHOICE {
        int id PK
        int menu_option_id FK
        string label
        decimal extra_price
    }
    DINING_TABLE {
        int id PK
        int outlet_id FK
        int number
        int capacity
        string qr_code
        string status
    }
    TABLE_SESSION {
        int id PK
        int table_id FK
        datetime opened_at
        datetime closed_at
        string status
    }
    CUSTOMER {
        int id PK
        string name
        string phone
        string email
    }
    VOUCHER {
        int id PK
        string code UK
        string discount_type
        decimal value
        decimal min_purchase
        datetime valid_from
        datetime valid_until
        int quota
    }
    STAFF {
        int id PK
        int outlet_id FK
        string name
        string username UK
        string password_hash
        string role
        boolean is_active
    }
    ORDERS {
        int id PK
        string order_number UK
        int session_id FK
        int customer_id FK
        int voucher_id FK
        int confirmed_by FK
        string status
        decimal subtotal
        decimal tax
        decimal service_charge
        decimal discount
        decimal total_amount
        string cancel_reason
        datetime created_at
    }
    ORDER_ITEM {
        int id PK
        int order_id FK
        int menu_item_id FK
        int quantity
        decimal unit_price
        string note
        string status
    }
    ORDER_ITEM_CHOICE {
        int order_item_id PK
        int option_choice_id PK
        decimal extra_price
    }
    PAYMENT {
        int id PK
        int order_id FK
        string method
        decimal amount
        string status
        datetime paid_at
        string transaction_ref
    }
    REVIEW {
        int id PK
        int order_id FK
        int rating
        text comment
        datetime created_at
    }
```

**Catatan desain database**

- `TABLE_SESSION` memastikan satu meja hanya punya satu sesi aktif dan satu tagihan.
- `OUTLET` disiapkan untuk dukungan multi-cabang.
- `unit_price` dan `extra_price` disimpan sebagai snapshot agar perubahan harga menu tidak mengubah pesanan lama.
- Cart cukup disimpan di sisi klien atau cache sementara, lalu menjadi `ORDERS` dan `ORDER_ITEM` saat checkout.

## Roadmap

- [x] Analisis kebutuhan dan aturan bisnis
- [x] Desain class, use case, dan ERD
- [ ] Implementasi backend (API menu, pesanan, pembayaran)
- [ ] Integrasi payment gateway (QRIS, e-wallet, kartu)
- [ ] Antarmuka pelanggan (mobile-first, tanpa instal)
- [ ] Kitchen display dan dashboard kasir real-time
- [ ] Dashboard admin dan laporan penjualan
- [ ] Dukungan multi-cabang

## Kontributor

| No | Nama | NIM | Peran |
|---|---|---|---|
| 1 | Farhat Bima Raditya (60225134) | [isi NIM] | Modul Menu |
| 2 | Zaki Rahul Fawas (60225135) | [isi NIM] | Modul Pesanan |
| 3 | Putra Agung Srihandaka (60225149) | [isi NIM] | Modul Pembayaran, Promo, dan Laporan |
| 4 | Muhammad Wafa (60225153) | [isi NIM] | Modul Meja, Staf, dan Dapur |
