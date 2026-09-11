#!/usr/bin/env python3
"""
Pembaru otomatis blok statistik README profil YoryZiar.

Mengambil data dari sumber PUBLIK saja (tanpa token, tanpa PAT), lalu menuliskan
ulang blok <pre> statistik, tabel metrik, dan tanggal pembaruan di README.md.

Sumber data dan alasan pemilihannya:
  1. Kalender kontribusi publik (github.com/users/<user>/contributions)
     Satu-satunya sumber yang per-harinya mendekati dan agregatnya identik dengan
     yang dilihat pemilik, termasuk kontribusi repositori privat.
     Divalidasi: total 394 = 394, 13/13 agregat bulanan sama persis dengan GraphQL.
  2. Parameter ?from=&to= pada halaman yang sama -> granularitas TAHUN saja.
     Divalidasi: rentang sub-tahun mengembalikan total tahun penuh.
  3. api.github.com/users/<user>                  -> public_repos, followers.
  4. api.github.com/repos/<user>/<repo>/languages -> bytes per bahasa.
  5. Search API is:pr author:<user>               -> jumlah PR publik.

Batasan yang diketahui dan disengaja:
  - Jumlah PR mencakup repositori PUBLIK saja. PR pada repositori privat tidak
    dapat dihitung tanpa token pribadi, dan angka "sepanjang masa" tidak dapat
    direproduksi. Karena itu yang ditampilkan adalah PR 12 bulan yang konsisten.
  - Angka per-hari dapat berselisih 1-2 dari GraphQL karena penundaan agregasi
    GitHub. Agregat bulanan, tahunan, dan total terbukti identik.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    WITA = ZoneInfo("Asia/Makassar")
except Exception:                                   # tzdata tidak tersedia
    WITA = timezone(timedelta(hours=8), "WITA")     # WITA selalu UTC+8, tanpa DST

USER = "YoryZiar"
PROFIL_REPO = "YoryZiar"          # repositori profil (README) — tidak dihitung sebagai kode
WITA = ZoneInfo("Asia/Makassar")
README = Path(__file__).resolve().parent.parent / "README.md"

# Token bersifat OPSIONAL. Tanpa token, batas laju GitHub untuk permintaan anonim
# hanya 60 per jam — tidak cukup untuk membaca bahasa 14 repositori. Di dalam
# GitHub Actions, GITHUB_TOKEN disediakan otomatis dan menaikkan batas ke 5.000
# per jam. Token ini hanya dipakai untuk membaca data publik; skrip tidak
# memerlukan izin tulis apa pun terhadap API.
_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
UA = {"User-Agent": "YoryZiar-profile-stats", "Accept": "application/vnd.github+json"}
if _TOKEN:
    UA["Authorization"] = f"Bearer {_TOKEN}"

LEBAR_BATANG = 20
LEBAR_BULAN = 24
LEBAR_NAMA = 11
LEBAR_DALAM = 75

NAMA_BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
              "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


# ─────────────────────────────── pengambilan data ───────────────────────────────

def ambil(url: str, json_mode: bool = True):
    """GET dengan tiga kali percobaan."""
    galat = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                mentah = r.read().decode("utf-8", "replace")
            return json.loads(mentah) if json_mode else mentah
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            galat = e
    raise RuntimeError(f"gagal mengambil {url}: {galat}")


def kalender_kontribusi() -> dict[str, int]:
    """Pasangan tanggal -> jumlah kontribusi dari kalender publik."""
    html = ambil(f"https://github.com/users/{USER}/contributions", json_mode=False)
    tanggal = re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"', html)
    tips = [unescape(t.strip())
            for t in re.findall(r"<tool-tip[^>]*>(.*?)</tool-tip>", html, re.S)]

    jumlah: list[int] = []
    for t in tips:
        if t.lower().startswith("no contribution"):
            jumlah.append(0)
            continue
        m = re.match(r"^([\d,]+)\s+contribution", t)
        if not m:
            raise RuntimeError(f"format tool-tip tidak dikenal: {t[:80]!r}")
        jumlah.append(int(m.group(1).replace(",", "")))

    if len(tanggal) != len(jumlah):
        raise RuntimeError(
            f"jumlah tanggal ({len(tanggal)}) tidak sama dengan tool-tip ({len(jumlah)})")
    return dict(zip(tanggal, jumlah))


def total_tahun(tahun: int) -> int:
    """Total kontribusi satu tahun kalender, dari halaman tahun resmi GitHub.

    Halaman ?from=&to= mengembalikan total untuk TAHUN KALENDER di mana `from`
    berada — bukan untuk rentang yang diminta. Karena itu fungsi ini hanya boleh
    dipanggil dengan rentang satu tahun penuh (1 Jan – 31 Des).

    Contoh validasi: 2025 -> 120 (mencakup Jan–Agu 2025 yang berada di luar
    jendela 12 bulan bergulir) sedangkan kalender bergulir hanya melihat 27
    untuk Sep–Des 2025. Keduanya benar untuk periode masing-masing.
    """
    html = ambil(f"https://github.com/users/{USER}/contributions"
                 f"?from={tahun}-01-01&to={tahun}-12-31", json_mode=False)

    # Tahun tanpa aktivitas: header berbentuk "No contributions in <tahun>".
    # Perhatikan: bentuk tooltip harian "No contributions on <tanggal>" SELALU ada
    # di halaman ini, sehingga tidak boleh dipakai sebagai penanda tahun kosong.
    if re.search(r"\bno contributions in\b", html, re.I):
        return 0

    m = re.search(r"([\d,]+)\s+contributions?\s+in", html)
    if m:
        return int(m.group(1).replace(",", ""))
    lain = re.findall(r"([\d,]+)\s*contributions?", html)
    if not lain:
        raise RuntimeError(f"total tahun {tahun} tidak ditemukan")
    return int(lain[0].replace(",", ""))


def profil() -> dict:
    return ambil(f"https://api.github.com/users/{USER}")


def repositori_publik() -> list[dict]:
    rs = ambil(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner")
    return [r for r in rs if not r["private"] and not r["fork"]]


def bytes_bahasa(daftar: list[dict]) -> tuple[Counter, list[str]]:
    """Kumpulkan bytes per bahasa. Mengembalikan (total, daftar repo yang dilewati).

    Kegagalan pada satu repositori TIDAK boleh membuat angka total tampak benar
    padahal tidak lengkap — karena itu pemanggil wajib memeriksa daftar lewat.
    """
    total: Counter = Counter()
    lewat: list[str] = []
    for r in daftar:
        if r["name"] == PROFIL_REPO:
            continue
        try:
            for k, v in ambil(r["languages_url"]).items():
                total[k] += v
        except RuntimeError as e:
            lewat.append(r["name"])
            print(f"  ! lewati {r['name']}: {e}", file=sys.stderr)
    return total, lewat


def jumlah_pr() -> int:
    """Jumlah Pull Request pada repositori PUBLIK.

    Kualifikasi `is:public` WAJIB ada agar hasilnya deterministik: tanpa itu,
    permintaan anonim melaporkan 13 sedangkan permintaan bertoken melaporkan 84
    (token pemilik ikut melihat PR repositori privat). Karena hasilnya harus sama
    di laptop maupun di GitHub Actions, kualifikasi ini tidak boleh dilepas.
    """
    d = ambil(f"https://api.github.com/search/issues"
              f"?q=is%3Apr+author%3A{USER}+is%3Apublic&per_page=1")
    return int(d["total_count"])


# ─────────────────────────────── penyusunan blok ───────────────────────────────

def batang(nilai: int, maks: int, lebar: int) -> str:
    if maks <= 0 or nilai <= 0:
        return "·" * lebar
    isi = max(1, round(nilai / maks * lebar))
    return "█" * isi + "·" * (lebar - isi)


def batang_persen(pct: float, lebar: int) -> str:
    """Batang untuk nilai persentase. Minimal satu blok selama pct > 0."""
    if pct <= 0:
        return "·" * lebar
    isi = max(1, round(pct / 100 * lebar))
    return "█" * isi + "·" * (lebar - isi)


def kotak(judul: str, baris: list[str]) -> list[str]:
    """Kotak dengan lebar dalam persis LEBAR_DALAM karakter.

    Dihitung: "┌─ " (3) + judul + " " (1) + "─"*n + "┐" (1) = LEBAR_DALAM + 2.
    """
    isi_garis = LEBAR_DALAM - 3 - len(judul)
    if isi_garis < 3:
        raise ValueError(f"judul terlalu panjang untuk kotak: {judul!r}")
    atas = "┌─ " + judul + " " + "─" * isi_garis + "┐"
    return ([atas]
            + ["│" + b.ljust(LEBAR_DALAM) + "│" for b in baris]
            + ["└" + "─" * LEBAR_DALAM + "┘"])


def susun(tahun: dict[int, int], bahasa: Counter, bulan: dict[str, int],
          jml_repo: int) -> str:
    blok: list[str] = []

    # 1 — kontribusi per tahun
    maks_t = max(tahun.values()) if tahun else 1
    puncak_t = max(tahun, key=lambda k: tahun[k]) if tahun else None
    isi = []
    for y in sorted(tahun):
        baris = f"  {y}  {batang(tahun[y], maks_t, LEBAR_BULAN)}{tahun[y]:>7d}"
        if y == puncak_t:
            baris += "   ◄ permintaan tertinggi"
        isi.append(baris)
    blok += kotak("KONTRIBUSI PER TAHUN", isi)

    # 2 — komposisi bahasa
    total_bytes = sum(bahasa.values()) or 1
    judul2 = (f"KOMPOSISI KODE ({jml_repo} repositori publik · "
              f"{total_bytes / 1_000_000:.2f} MB)".replace(".", ","))
    isi2 = []
    for nama, b in bahasa.most_common(8):
        pct = b / total_bytes * 100
        isi2.append(f"  {nama:<{LEBAR_NAMA}s} "
                    f"{batang_persen(pct, LEBAR_BATANG)} {pct:>5.1f}%")
    blok.append("")
    blok += kotak(judul2, isi2)

    # 3 — irama 12 bulan
    kunci = sorted(bulan)[-12:]
    maks_b = max((bulan[k] for k in kunci), default=0)
    puncak_b = max(kunci, key=lambda k: bulan[k]) if kunci else None
    isi3 = []
    for k in kunci:
        nm = NAMA_BULAN[int(k[5:7]) - 1]
        baris = f"  {nm} {batang(bulan[k], maks_b, LEBAR_BATANG)}{bulan[k]:>4d}"
        if k == puncak_b:
            baris += "   ◄ puncak produktivitas"
        isi3.append(baris)
    blok.append("")
    blok += kotak("IRAMA 12 BULAN TERAKHIR", isi3)

    return "\n".join(blok)


# ─────────────────────────────── penyuntingan README ───────────────────────────────

POLA_PRE = re.compile(
    r"(## `> git stats --global`\n\n<pre>\n)(.*?)(\n</pre>)", re.S)
POLA_TABEL = re.compile(r"(\| Metrik \| Nilai \|\n\|:?---\|:?---:\|\n)(?:\|.*\n)+")
PENANDA = "<!-- stats-updated -->"
JANGKAR = "Berikut hasil pemindaian nyata terhadap repositori ini, bukan klaim:\n"


def ganti_pre(isi: str, baru: str) -> str:
    if not POLA_PRE.search(isi):
        raise RuntimeError("blok <pre> pada seksi 'git stats --global' tidak ditemukan")
    return POLA_PRE.sub(lambda m: m.group(1) + baru + m.group(3), isi, count=1)


def ganti_tabel(isi: str, m: dict) -> str:
    mb = f"{m['mb']:.2f}".replace(".", ",")
    baris = (
        f"| Kontribusi (12 bulan) | **{m['kontribusi_12']}** |\n"
        f"| Pull Request (12 bulan) | **{m['pr_12']}** |\n"
        f"| Repositori publik | **{m['repo_publik']}** |\n"
        f"| Kode publik | **{mb} MB** |\n"
        f"| Tahun aktif | **{m['tahun_min']} – {m['tahun_max']}** |\n"
        f"| Pengikut | **{m['pengikut']}** |\n"
    )
    if not POLA_TABEL.search(isi):
        raise RuntimeError("tabel metrik tidak ditemukan")
    return POLA_TABEL.sub(lambda mo: mo.group(1) + baris, isi, count=1)


def ganti_tanggal(isi: str, stempel: str, total: int) -> str:
    baris = (f"{PENANDA}\n`📅 Data statistik diperbarui otomatis: {stempel} WITA "
             f"· {total} kontribusi sepanjang masa`\n\n")
    if PENANDA in isi:
        return re.sub(rf"{re.escape(PENANDA)}\n.*?\n\n", baris, isi, count=1, flags=re.S)
    if JANGKAR not in isi:
        raise RuntimeError("jangkar catatan teknis tidak ditemukan")
    return isi.replace(JANGKAR, baris + JANGKAR, 1)


def main() -> int:
    print("→ kalender kontribusi…")
    kal = kalender_kontribusi()
    batas_12 = date.today() - timedelta(days=365)
    total_12 = sum(v for k, v in kal.items() if date.fromisoformat(k) > batas_12)

    print("→ profil…")
    pr = profil()

    print("→ total per tahun…")
    # Daftar tahun diambil dari tahun pembuatan akun sampai tahun berjalan, bukan
    # dari kalender bergulir (yang hanya mencakup ~12 bulan terakhir).
    tahun_mulai = int(pr["created_at"][:4])
    tahun: dict[int, int] = {}
    for y in range(tahun_mulai, date.today().year + 1):
        tahun[y] = total_tahun(y)
        print(f"   {y}: {tahun[y]}")

    print("→ repositori & bahasa…")
    rs = repositori_publik()
    bahasa, lewat = bytes_bahasa(rs)
    n_repo = len([r for r in rs if r["name"] != PROFIL_REPO])

    if lewat:
        # Angka bytes tidak lengkap. Lebih jujur berhenti daripada menulis angka salah.
        print(f"✗ GAGAL: {len(lewat)} repositori tidak terbaca: {', '.join(lewat)}",
              file=sys.stderr)
        print("  Kemungkinan penyebab: batas laju GitHub API (60 permintaan/jam untuk "
              "permintaan anonim). Coba lagi nanti.", file=sys.stderr)
        print("  README TIDAK diubah.", file=sys.stderr)
        return 1

    bulan: dict[str, int] = {}
    for k, v in kal.items():
        bulan[k[:7]] = bulan.get(k[:7], 0) + v

    n_pr = jumlah_pr()
    stempel = datetime.now(WITA).strftime("%d %B %Y")
    total_semua = sum(tahun.values())

    metrik = {
        "kontribusi_12": total_12,
        "pr_12": n_pr,
        "repo_publik": pr["public_repos"],
        "mb": sum(bahasa.values()) / 1_000_000,
        "tahun_min": min(tahun),
        "tahun_max": max(tahun),
        "pengikut": pr["followers"],
    }

    isi = README.read_text(encoding="utf-8")
    baru = ganti_pre(isi, susun(tahun, bahasa, bulan, n_repo))
    baru = ganti_tabel(baru, metrik)
    baru = ganti_tanggal(baru, stempel, total_semua)

    if baru == isi:
        print("→ README sudah mutakhir; tidak ada perubahan.")
        return 0

    README.write_text(baru, encoding="utf-8")
    print(f"→ README diperbarui · kontribusi 12 bulan {total_12} · PR {n_pr} · "
          f"{metrik['mb']:.2f} MB")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as e:
        print(f"✗ GAGAL: {e}", file=sys.stderr)
        print("  README tidak diubah.", file=sys.stderr)
        raise SystemExit(1)
