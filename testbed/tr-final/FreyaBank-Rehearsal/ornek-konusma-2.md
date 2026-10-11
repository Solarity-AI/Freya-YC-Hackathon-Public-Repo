# Örnek Konuşma 2 — Asgari ödeme; 29 Ekim tatil, 30 Ekim önerilir

- Arama zamanı (`now`): `2026-10-27T14:00` (27 Ekim 2026 Salı, saat 14:00)
- Müşteri: `FB-240233` — Mehmet Kaya (Bey)
- Çağrı değişkenleri: `{"musteri_no": "FB-240233", "ad": "Mehmet", "soyad": "Kaya", "hitap": "Bey", "now": "2026-10-27T14:00"}`

Servis çağrıları `[Servis]` satırlarında, gönderilen gövde ve gelen cevapla gösterilmiştir.

**Asistan:** Merhaba, ben Freya Bank'ın dijital asistanıyım. Bu görüşme kalite amacıyla kayıt altına alınmaktadır. Mehmet Kaya ile mi görüşüyorum?

**Müşteri:** Buyurun.

**Asistan:** Kusura bakmayın, Mehmet Kaya ile mi görüşüyorum?

**Müşteri:** Evet, Mehmet Kaya benim.

**Asistan:** Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?

**Müşteri:** Üç Ocak bin dokuz yüz seksen beş.

> [Servis] `KimlikDogrula` ← `{"musteri_no": "FB-240233", "soru": "DOGUM_TARIHI", "cevap": "03.01.1985"}` → `{"basarili": true, "dogrulandi": true, "kalan_hak": 3, "tum_sorular_tamam": false}`

**Asistan:** Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?

**Müşteri:** Altı altı bir dört.

> [Servis] `KimlikDogrula` ← `{"musteri_no": "FB-240233", "soru": "TCKN_SON4", "cevap": "6614"}` → `{"basarili": true, "dogrulandi": true, "kalan_hak": 3, "tum_sorular_tamam": true}`

> [Servis] `EkstreBorcSorgula` ← `{"musteri_no": "FB-240233"}` → `{"basarili": true, "kartlar": [{"kart_id": "KRT-240233-01", "urun": "KREDI_KARTI", "kart_son4": "2290", "ekstre_borcu": 5350.0, "asgari_odeme_tutari": 2140.0, "son_odeme_tarihi": "2026-10-05", "gecikme_gun_sayisi": 22}]}`

**Asistan:** Teşekkür ederim Mehmet Bey. Freya Bank tahsilat biriminden arıyorum. 2290 ile biten kredi kartınızın ekstre borcu 5.350,00 TL; son ödeme tarihi 5 Ekim idi ve ödeme 22 gündür gecikmede. Bu ödemeyi bugün yapabilir misiniz?

**Müşteri:** Bugün olmaz, hem tamamı benim için çok fazla.

**Asistan:** Anlıyorum. O halde asgari ödeme tutarı olan 2.140,00 TL ödenebilir. Kalan tutar gecikmede kalmaya devam eder. Bu tutarı hangi gün ödeyebilirsiniz?

**Müşteri:** Asgariyi 29 Ekim'de yatırırım.

**Asistan:** 29 Ekim resmi tatil. Bir sonraki iş günü olan 30 Ekim 2026 Cuma günü ödeyebilir misiniz?

**Müşteri:** Olur, cuma yatırırım.

**Asistan:** Özetliyorum: 2290 ile biten kredi kartınız için 2.140,00 TL, ödeme tarihi 30 Ekim 2026 Cuma. Onaylıyor musunuz?

**Müşteri:** Evet.

> [Servis] `OdemeSozuKaydet` ← `{"musteri_no": "FB-240233", "kart_id": "KRT-240233-01", "tutar": 2140.0, "odeme_tarihi": "2026-10-30", "soz_tipi": "ASGARI"}` → `{"basarili": true, "soz_no": "SZ-1002"}`

**Asistan:** Ödeme sözünüz kaydedildi. Bu ödeme sözünü onaylayan bir SMS alacaksınız.

**Müşteri:** Tamam, sağ olun.

**Asistan:** Zaman ayırdığınız için teşekkür ederim, iyi günler dilerim.

> [Servis] `GorusmeKapat` ← `{"musteri_no": "FB-240233", "sonuc_kodu": "SOZ_ALINDI"}` → `{"basarili": true}`
