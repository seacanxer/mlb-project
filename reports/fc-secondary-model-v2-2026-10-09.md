# FC corner / kartu v2 — hasil implementasi

## Keluaran card

- Corner: proyeksi total dan masing-masing tim, pemenang jumlah corner (termasuk hasil sama banyak), Asian handicap, dan O/U.
- Kartu: proyeksi poin per tim/total, tim dengan poin lebih banyak (termasuk sama banyak), Asian handicap, O/U total/per tim, serta kartu merah Ya/Tidak.
- Satuan kartu dinyatakan sebagai poin: kuning = 1, merah = 2. Semua keluaran masih proyeksi penelitian, bukan Official.

## Perbaikan perhitungan dan input

1. Nama tim dinormalisasi sebelum menggabungkan histori. Contoh Dortmund dan Borussia Dortmund sekarang menjadi satu identitas. Duplikat dengan skor bertentangan tidak digabung.
2. Baris tim di luar roster liga dikeluarkan dari input model domestik. Importer FotMob berikutnya membutuhkan negara dan nama kompetisi sesuai registry; Bundesliga Austria tidak masuk Bundesliga Jerman.
3. Pertahanan tim kandang memakai baseline corner/kartu tim tamu, dan sebaliknya. Perhitungan lama memakai baseline mencetak gol untuk statistik kebobolan, sehingga faktor home/away dapat bias.
4. Total, pemenang dan handicap berasal dari distribusi hitungan yang sama. Total poin kartu merupakan konvolusi distribusi poin kedua tim.
5. Line proyeksi total menggunakan garis terdekat dengan mean model. Model tidak memilih garis lebih rendah hanya untuk memperbesar probabilitas Over.
6. Semua line corner yang ditawarkan dievaluasi, termasuk quarter 0,25/0,75. Harga dengan key JSON string juga terbaca. EV menghitung half-win, push dan half-loss; effective win probability = full-win + 0,5 × half-win.
7. Kartu merah yang tidak tercatat tetap dianggap tidak tersedia. Histori dengan nol kartu merah menggunakan prior Gamma(0,5; 0,5), sehingga proyeksi Tidak tidak menjadi 100% hanya karena sampel terbatas.

Kriteria histori tetap: effective sample liga minimal 30 dan masing-masing peran tim minimal 3. Probabilitas v2 belum dikalibrasi dengan hasil pertandingan mendatang.

## Fetch odds

Adapter 1xbit sekarang memverifikasi ID fixture/subgame/parent, mengecualikan babak pertama/kedua, membaca struktur nested dan kode numerik/string, menolak harga non-finite, serta melakukan maksimal dua percobaan untuk gangguan jaringan. Setiap pasar mempunyai status fetch dan waktu pengambilan sendiri. Fetch gagal tidak memakai cache lama.

Odds kartu TI=10 belum digunakan untuk menghitung EV poin kartu karena satuan kontraknya belum terverifikasi. Pemenang corner/kartu dan prediksi merah tetap tersedia sebagai proyeksi tanpa harga jika odds yang cocok belum tersedia.

Ledger penelitian mencatat market baru dan versi formula. Grading menggunakan statistik yang diperlukan per market: grading corner tidak menunggu data kartu. Audit ini tidak menjalankan settlement atau staking produksi.

## Audit live read-only, 9 Oktober 2026

Snapshot akhir: 150 fixture dari feed 24 jam; 16 memiliki histori cukup untuk sedikitnya satu kelompok corner/kartu. Dua fixture diuji sampai publikasi pick. Masing-masing menghasilkan 8 market proyeksi.

| Fixture | Projection corner | Poin kartu total | Line OU corner tersedia | Leg AH corner tersedia | OU terpilih | AH terpilih |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Borussia Dortmund vs Werder Bremen | 10,26 | 3,42 | 25 | 18 | Over 9,5 @1,92 | Werder Bremen +3 @1,93 |
| Mainz vs Leverkusen | 10,54 | 3,82 | 24 | 16 | Over 10 @1,87 | Mainz +1 @1,54 |

Pick Mainz mempunyai EV model negatif (OU −3,42%; AH −6,87%), sehingga tetap proyeksi dan bukan kandidat value/Official. Harga adalah snapshot waktu fetch, bukan closing odds. Data lengkap: `fc-secondary-live-audit-2026-10-09.json`.

Belum ada hasil pertandingan dari audit ini untuk menghitung win rate, Brier, log loss atau ROI v2. Pengujian perangkat lunak tidak membuktikan peningkatan akurasi prediksi.

## Verifikasi

- Suite Python lengkap: 336 lulus. Regression akhir corner/fetch/ingestion/ledger: 43 lulus setelah koreksi metadata ledger.
- Frontend: 239 lulus; TypeScript typecheck lulus.
- Komponen dirender dengan data audit pada browser headless desktop 1120 px dan mobile 390 px; tidak ada overflow horizontal. Preview PNG merupakan render lokal komponen, bukan screenshot situs VPS.

## Penggunaan

Setelah deployment kode, jalankan scan baru untuk menghasilkan data dengan market v2. Audit mandiri tanpa menyentuh output live:

```powershell
python scripts/fc-audit-secondary-live.py --limit 3 --output reports/fc-secondary-audit.json
```

Untuk satu fixture gunakan `--match-id ID_PROVIDER`. Histori yang belum cukup menghasilkan status tidak tersedia, bukan angka atau odds buatan.
