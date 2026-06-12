# CMM Quality Dashboard

Dashboard kualitas pengukuran **CMM (Coordinate Measuring Machine)** untuk PT Astra Honda Motor (AHM). Aplikasi berbasis **Streamlit** ini memonitor hasil pengukuran produksi secara real-time, menganalisis penyebab NG (Not Good), serta memprediksi risiko cacat ke depan menggunakan model AI (XGBoost & ARIMA) dan aturan statistik SPC.

Dokumen ini ditujukan agar developer baru bisa cepat memahami dan melanjutkan proyek.

---

## Daftar Isi

1. [Fitur Utama](#fitur-utama)
2. [Tumpukan Teknologi](#tumpukan-teknologi)
3. [Struktur Proyek](#struktur-proyek)
4. [Prasyarat](#prasyarat)
5. [Instalasi & Menjalankan](#instalasi--menjalankan)
6. [Konfigurasi](#konfigurasi)
7. [Sumber Data](#sumber-data)
8. [Model Machine Learning](#model-machine-learning)
9. [Halaman Aplikasi](#halaman-aplikasi)
10. [Login & Role](#login--role)
11. [Arsitektur & Alur Data](#arsitektur--alur-data)
12. [Catatan untuk Pengembangan Lanjutan](#catatan-untuk-pengembangan-lanjutan)
13. [Troubleshooting](#troubleshooting)

---

## Fitur Utama

- **Dashboard real-time** — KPI rasio OK, total titik/part NG, alert NG aktual, prediksi NG shift berikutnya, dan status per mesin CMM.
- **Analitik berjenjang** mengikuti piramida analytics:
  - *Descriptive* — drill-down Pareto & investigasi mendalam.
  - *Diagnostic* — Root Cause Analysis (input & riwayat penyebab NG).
  - *Predictive* — klasifikasi risiko NG (XGBoost), forecasting nilai (ARIMA), dan deteksi 7 Nelson rules (SPC).
  - *Prescriptive* — rekomendasi tindakan berbasis prioritas.
- **Sistem pesan & notifikasi** — notifikasi NG otomatis dari laporan ke tim Produksi, lengkap dengan badge unread.
- **Report Hub** — pembuatan laporan inspeksi QCL (WSIRD Produksi) dan export Excel/PDF.
- **Floating chatbot AI** — asisten berbasis Google Gemini yang menjawab pertanyaan berdasarkan data produksi.
- **Pengaturan** — target OK rate dan target jumlah sample per shift.

---

## Tumpukan Teknologi

| Kategori | Paket utama |
|----------|-------------|
| UI / Framework | `streamlit`, `streamlit-option-menu`, `streamlit-echarts`, `streamlit-antd-components`, `streamlit-autorefresh` |
| Data | `pandas`, `numpy`, `scipy`, `pytz` |
| Machine Learning | `xgboost`, `scikit-learn`, `joblib`, `pmdarima` (ARIMA) |
| Laporan | `openpyxl`, `pywin32` (opsional, untuk PDF via Excel di Windows) |
| AI Chatbot | `google-genai` (Gemini) |

Versi lengkap & ter-pin ada di [`requirements.txt`](requirements.txt). Dikembangkan dengan **Python 3.12**.

---

## Struktur Proyek

```
CMM QUALITY DASHBOARD/
├── mainloca.py              # Entry point: login, sidebar, routing, CSS global
├── floating_chatbot.py      # Asisten AI mengambang (Gemini)
├── local_db.py              # Lapisan penyimpanan lokal (CSV + JSON)
├── settings_config.py       # Baca/tulis data/settings.json
├── requirements.txt         # Dependensi Python
│
├── pages_app/               # Satu file = satu halaman (class *Page)
│   ├── dashboard.py         # Dashboard ringkasan real-time
│   ├── descriptive.py       # Descriptive analytics
│   ├── diagnostic.py        # Root Cause Analysis
│   ├── predictive.py        # AI Predictive (XGBoost/ARIMA) + SPC
│   ├── prescriptive.py      # Rekomendasi tindakan
│   ├── messages.py          # Pesan & notifikasi NG
│   ├── report.py            # Report Hub (QCL inspection, export)
│   └── settings.py          # Pengaturan target OK & sample
│
├── utils/
│   ├── filters.py           # Filter bersama (part/model/tanggal/CMM)
│   └── xgb_inference.py     # Inference XGBoost & rule SPC (shared cache)
│
├── models/                  # Model terlatih per titik ukur
│   ├── xgb_<TITIK>.pkl       # Model XGBoost
│   ├── encoders_<TITIK>.pkl  # LabelEncoder fitur kategorikal
│   └── model_info_<TITIK>.json # Metadata fitur model
│
├── assets/                  # Logo, ilustrasi titik ukur, template Excel
│   ├── Logo_AHM.svg
│   ├── ilustrasi/           # Gambar per model + ilustrasi 7 rule SPC
│   └── templates/           # Template Excel laporan (K2VJ.xlsx, K60.xlsx)
│
├── data/                    # Penyimpanan runtime (dibuat otomatis)
│   ├── reports.csv          # Metadata laporan
│   ├── messages.csv         # Inbox notifikasi
│   ├── ng_notifs.csv        # Notifikasi NG detail
│   ├── root_causes.csv      # Root cause yang diinput
│   ├── settings.json        # Konfigurasi (dibuat saat pertama simpan)
│   └── reports/<id>.json    # Data laporan lengkap per laporan
│
├── REALNEO.csv              # Dataset pengukuran utama (besar, dipakai semua halaman)
├── REAL7D.csv               # Dataset 7 hari terakhir (dipakai chatbot)
│
└── .streamlit/
    ├── config.toml          # Tema warna aplikasi
    └── secrets.toml          # Kredensial (API key Gemini) — JANGAN commit
```

---

## Prasyarat

- **Python 3.12** (disarankan, sesuai environment pengembangan).
- **pip** untuk memasang dependensi.
- (Opsional) **Microsoft Excel + Windows** bila ingin fitur export PDF laporan.
- **API key Google Gemini** bila ingin mengaktifkan chatbot.

---

## Instalasi & Menjalankan

```bash
# 1. (Disarankan) buat virtual environment
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate      # Linux/Mac

# 2. Pasang dependensi
pip install -r requirements.txt

# 3. Jalankan aplikasi
streamlit run mainloca.py
```

Aplikasi terbuka di browser pada `http://localhost:8501`.

> **Catatan:** file `REALNEO.csv` (dataset utama) dan `REAL7D.csv` (untuk chatbot) harus ada di root proyek. Folder `data/` dibuat otomatis saat aplikasi pertama dijalankan.

---

## Konfigurasi

### 1. Tema warna — `.streamlit/config.toml`
Mendefinisikan palet warna agar widget native Streamlit selaras dengan CSS custom (merah brand AHM `#DC2626`, latar putih, sekunder `#F1F4F9`). Edit di sini bila ingin ubah skema warna global.

### 2. Rahasia — `.streamlit/secrets.toml`
Berisi API key untuk chatbot:

```toml
GEMINI_API_KEY = "xxxxxxxxxxxxxxxxxxxx"
```

Tanpa key ini, chatbot menampilkan pesan konfigurasi gagal — fitur lain tetap berjalan normal. **Jangan commit file ini ke repository publik.**

### 3. Target kualitas — Halaman Pengaturan / `data/settings.json`
Diatur lewat UI (halaman Pengaturan) atau langsung di `settings.json`:
- `target_ok_global` — target rasio OK (%) global, default `98.65`.
- `sample_targets` — jumlah sample per shift dengan format key `"{Part}|{Model}|{Cycle}"`.

Default ada di `settings_config.py` (`DEFAULTS`).

---

## Sumber Data

### Dataset pengukuran utama (`REALNEO.csv`)
Dibaca di `mainloca.py` (`load_data`) dan diteruskan ke semua halaman. Skema kolom:

| Kolom | Keterangan |
|-------|-----------|
| `Date` | Tanggal pengukuran |
| `Shift` | Shift (1/2/3) |
| `Cycle` | Siklus produksi |
| `SampleNo` | Nomor sample |
| `PartName` | Nama part (mis. CYL COMP, CRCS L) |
| `ModelName` | Model mesin/line (mis. K60, K1AL L1) |
| `CMMName` | Nama mesin CMM |
| `ref` | Referensi titik ukur |
| `ID` | ID titik (fallback `ref`) |
| `point` | Nama titik ukur (fallback `Parameter`) |
| `Parameter` | Parameter geometris (posisi, diameter, dll.) |
| `Nominal` | Nilai nominal target |
| `Uppertol` / `Lowertol` | Toleransi atas / bawah |
| `Actual` | Nilai aktual hasil ukur |
| `Deviation` | Deviasi terhadap nominal |
| `Judgement` | `OK` / `NG` |
| `KP` | Kritikal Point (1 = kritikal) |
| `Category` | Kategori data (mis. Produksi) |

### Penyimpanan runtime (`data/`)
Dikelola oleh `local_db.py` (CSV + JSON). Lihat docstring file tersebut untuk skema kolom tiap CSV. Catatan penting dari kode: lapisan ini sengaja dibuat agar mudah **migrasi ke Supabase** — cukup ganti implementasi fungsi di `local_db.py` tanpa mengubah pemanggil di `report.py`/`messages.py`.

---

## Model Machine Learning

Semua model terlatih ada di folder `models/`, dengan konvensi penamaan per titik ukur `<TITIK>` (mis. `CRCS_L_K1AL_L1`):

- `xgb_<TITIK>.pkl` — model **XGBoost** klasifikasi NG/OK.
- `encoders_<TITIK>.pkl` — `LabelEncoder` untuk fitur kategorikal.
- `model_info_<TITIK>.json` — metadata fitur yang dibutuhkan model.

**Inference** ditangani `utils/xgb_inference.py`:
- Dijalankan **sekali per sesi per shift**, hasil di-cache 30 menit (`TTL_SECONDS`).
- Cache key sama persis antara Dashboard dan Predictive (`xgb_cls_v2_{next_shift}_{next_date}`), jadi tidak menghitung ulang antar halaman.
- Shift berikutnya dideteksi otomatis dari jam WIB (Shift 1: 07–16, Shift 2: 16–24, Shift 3: 00–07).

**Forecasting** (`predictive.py`) memakai `pmdarima.auto_arima` untuk memproyeksikan deviasi ke depan dan menaksir kapan titik melewati toleransi.

**Deteksi SPC** mengimplementasikan **7 Nelson rules** (`_detect_kendali_shared`) untuk mendeteksi proses di luar kendali, lalu memproyeksikan tren linier.

---

## Halaman Aplikasi

| Halaman | File | Fungsi |
|---------|------|--------|
| **Dashboard** | `dashboard.py` | KPI real-time, alert NG/prediksi/SPC, status mesin CMM |
| **Descriptive** | `descriptive.py` | Drill-down Pareto + investigasi mendalam dengan ilustrasi titik |
| **Diagnostic** | `diagnostic.py` | Input & riwayat Root Cause Analysis per titik NG |
| **Predictive** | `predictive.py` | Klasifikasi risiko (XGBoost), Forecasting (ARIMA), Deteksi SPC |
| **Prescriptive** | `prescriptive.py` | Prioritas tindakan & rekomendasi berbasis RC historis |
| **Pesan** | `messages.py` | Notifikasi NG otomatis, input root cause dari Produksi |
| **Laporan** | `report.py` | Buat/lihat/export laporan inspeksi QCL |
| **Pengaturan** | `settings.py` | Target OK rate & target sample per shift |

> Setiap halaman adalah sebuah class (`DashboardPage`, `PredictivePage`, dst.) dengan method `render()`. Routing diatur di `mainloca.py` melalui `page_map`. Untuk menambah halaman baru: buat class baru di `pages_app/`, daftarkan di `ALL_PAGES`, `PAGE_ICONS`, `PAGE_LABELS`, dan `page_map`.

---

## Login & Role

Kredensial didefinisikan di `mainloca.py` (`USERS`). Default (untuk pengembangan):

| Username | Password | Role |
|----------|----------|------|
| `admin` | `admin` | Admin |
| `cmm` | `cmm` | Measurement |
| `produksi` | `produksi` | Produksi |

Akses halaman per role diatur di `ROLE_PAGES` (saat ini semua role mengakses semua halaman).

> ⚠️ **Keamanan:** kredensial saat ini disimpan plaintext di kode untuk kemudahan pengembangan. Sebelum dipakai produksi, pindahkan ke `secrets.toml`/database dan gunakan hash password.

---

## Arsitektur & Alur Data

```
                ┌──────────────────────────┐
                │       mainloca.py         │  ← entry, login, sidebar, routing
                └────────────┬─────────────┘
                             │ df_all (REALNEO.csv)
        ┌────────────────────┼─────────────────────┐
        ▼                    ▼                     ▼
   pages_app/*.py      utils/filters.py     utils/xgb_inference.py
   (8 halaman)         (filter bersama)     (inference + cache shared)
        │                                          │
        ▼                                          ▼
   local_db.py  ◄── notifikasi/laporan/RC      models/*.pkl
   settings_config.py ◄── target OK & sample
        │
        ▼
   data/ (CSV + JSON)
```

Alur tipikal:
1. `mainloca.py` memuat `REALNEO.csv` sekali (cache 5 menit) lalu *warmup* inference XGBoost & rule SPC.
2. User memilih halaman → class `*Page` dirender dengan `df_all` yang sama.
3. Filter (part/model/tanggal/CMM) dibangun lewat `utils/filters.py` dengan state bersama antar halaman terkait.
4. Notifikasi NG, root cause, dan laporan disimpan ke `data/` via `local_db.py`.

---

## Catatan untuk Pengembangan Lanjutan

- **Tema & CSS** terpusat di `mainloca.py` (`apply_custom_css`) + `.streamlit/config.toml`. Hindari menyebar `<style>` di tiap halaman; gunakan class yang sudah ada (`.kpi-card`, `.page-hdr`, `.section-desc`, `.kpi-sub`, dll.).
- **Animasi alert** di Dashboard menghormati `prefers-reduced-motion` dan pause saat di-hover (lihat blok CSS `.ng-alert-bar`/`.alert-carousel`/`.rule-alert-bar`).
- **Bahasa UI** memakai Bahasa Indonesia, kecuali istilah teknis/ilmiah (OK, NG, SPC, ARIMA, XGBoost, Forecasting, Descriptive/Diagnostic/Predictive/Prescriptive) yang dipertahankan.
- **Caching:** banyak fungsi memakai `@st.cache_data`/`@st.cache_resource`. Setelah mengubah model atau struktur data, gunakan tombol *Refresh* di Dashboard atau bersihkan cache agar hasil ter-update.
- **Migrasi database:** untuk pindah dari CSV ke DB (mis. Supabase), cukup ganti isi fungsi di `local_db.py` — interface ke halaman tetap.

---

## Troubleshooting

| Masalah | Penyebab & solusi |
|---------|-------------------|
| `File CSV tidak ditemukan: REALNEO.csv` | Pastikan `REALNEO.csv` ada di root proyek. |
| Chatbot menampilkan "Konfigurasi gagal" | `GEMINI_API_KEY` belum diisi di `.streamlit/secrets.toml`. |
| Fitur PDF laporan tidak aktif | `pywin32` belum terpasang atau bukan Windows + Excel. Uncomment `pywin32` di `requirements.txt`. |
| Prediksi kosong / "Tidak ada hasil prediksi" | Folder `models/` kosong atau data tidak cukup (min. observasi per titik). |
| Warna widget terlihat menyatu dengan latar | Pastikan `.streamlit/config.toml` ada; restart `streamlit`. |
| Perubahan data tidak muncul | Cache masih aktif (TTL 5–30 menit). Klik *Refresh* di Dashboard. |

---

*Dokumentasi ini melengkapi docstring di tiap file. Untuk detail implementasi, lihat komentar di dalam kode masing-masing modul.*
