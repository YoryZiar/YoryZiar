#!/usr/bin/env python3
"""
Uji mandiri untuk scripts/update_stats.py — tanpa jaringan, tanpa dependensi luar.

Dijalankan dengan:  python3 tests/test_render.py

Yang diuji:
  1. Setiap baris kotak memiliki lebar dalam yang sama dengan garis atas/bawah.
  2. Batang grafik tidak pernah nol untuk nilai positif (termasuk persen kecil).
  3. Penanda "puncak" hanya muncul sekali per blok.
  4. Penyuntingan README bersifat idempoten pada blok tiruan.
  5. Format angka mengikuti konvensi Indonesia (koma sebagai pemisah desimal).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import update_stats as us   # noqa: E402

gagal: list[str] = []


def cek(kondisi: bool, pesan: str) -> None:
    if kondisi:
        print(f"  ✓ {pesan}")
    else:
        print(f"  ✗ {pesan}")
        gagal.append(pesan)


print("1. Lebar kotak seragam")
tahun = {2022: 1, 2023: 26, 2024: 75, 2025: 120, 2026: 367}
bahasa = us.Counter({"TypeScript": 652_281, "PHP": 104_561, "EJS": 5_374})
bulan = {f"2025-{m:02d}": v for m, v in
         zip(range(10, 13), [10, 0, 3])}
bulan |= {f"2026-{m:02d}": v for m, v in
          zip(range(1, 10), [0, 26, 33, 11, 19, 22, 129, 73, 54])}

teks = us.susun(tahun, bahasa, bulan, 14)
baris = teks.split("\n")
lebar = {len(b) for b in baris if b.strip()}
cek(len(lebar) == 1, f"seluruh {len(baris)} baris berlebar sama: {sorted(lebar)}")
cek(lebar == {77}, f"lebar tepat 77 (aturan README): {sorted(lebar)}")

print("\n2. Batang tidak pernah kosong untuk nilai positif")
cek(us.batang_persen(0.5, 20).count("█") >= 1, "persen 0,5% tetap tampil satu blok")
cek(us.batang_persen(64.8, 20).count("█") == 13, "64,8% memakai 13 blok")
cek(us.batang_persen(0, 20) == "·" * 20, "persen 0 menjadi titik semua")
cek(us.batang(1, 367, 24).count("█") >= 1, "nilai tahun terkecil tetap tampil")

print("\n3. Penanda puncak muncul tepat sekali per blok")
cek(teks.count("◄ permintaan tertinggi") == 1, "satu penanda permintaan tertinggi")
cek(teks.count("◄ puncak produktivitas") == 1, "satu penanda puncak produktivitas")
cek("2026" in teks and teks.index("2026") < teks.index("◄ permintaan tertinggi"),
    "penanda tertinggi berada pada baris 2026")

print("\n4. Idempotensi penyuntingan blok <pre>")
contoh = "## `> git stats --global`\n\n<pre>\nblok lama\n</pre>\n\nsesudah\n"
sekali = us.ganti_pre(contoh, teks)
dua = us.ganti_pre(sekali, teks)
cek(sekali == dua, "menyunting dua kali menghasilkan isi identik")
cek("blok lama" not in sekali, "blok lama benar-benar tergantikan")
cek(sekali.endswith("sesudah\n") or "sesudah" in sekali, "teks setelah </pre> tidak rusak")

print("\n5. Format angka Indonesia")
isi = ("| Metrik | Nilai |\n|---|:---:|\n| lama | x |\n\nsetelah\n")
m = {"kontribusi_12": 394, "pr_12": 13, "repo_publik": 15,
     "mb": 1.006359, "tahun_min": 2022, "tahun_max": 2026, "pengikut": 10}
hasil = us.ganti_tabel(isi, m)
cek("**1,01 MB**" in hasil, "desimal memakai koma: 1,01 MB")
cek("**394**" in hasil and "**13**" in hasil, "angka metrik tertulis")
cek("setelah" in hasil, "teks setelah tabel tetap ada")

print(f"\n{'─' * 60}")
if gagal:
    print(f"GAGAL: {len(gagal)} pemeriksaan tidak lulus")
    for g in gagal:
        print(f"  - {g}")
    raise SystemExit(1)
print("SEMUA PEMERIKSAAN LULUS")
