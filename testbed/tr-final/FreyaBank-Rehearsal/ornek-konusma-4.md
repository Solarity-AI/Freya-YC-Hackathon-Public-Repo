# Örnek Konuşma 4 — Gün-ay ters ipucu; sonra 'dün ödedim'

- Arama zamanı (`now`): `2026-10-22T11:00` (22 Ekim 2026 Perşembe, saat 11:00)
- Müşteri: `FB-240402` — Can Öztürk (Bey)
- Çağrı değişkenleri: `{"musteri_no": "FB-240402", "ad": "Can", "soyad": "Öztürk", "hitap": "Bey", "now": "2026-10-22T11:00"}`

Servis çağrıları `[Servis]` satırlarında, gönderilen gövde ve gelen cevapla gösterilmiştir.

**Asistan:** Merhaba, ben Freya Bank'ın dijital asistanıyım. Bu görüşme kalite amacıyla kayıt altına alınmaktadır. Can Öztürk ile mi görüşüyorum?

**Müşteri:** Benim, buyurun.

**Asistan:** Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?

**Müşteri:** Dört dokuz yetmiş dokuz.

> [Servis] `KimlikDogrula` ← `{"musteri_no": "FB-240402", "soru": "DOGUM_TARIHI", "cevap": "04.09.1979"}` → `{"basarili": true, "dogrulandi": false, "kalan_hak": 3, "tum_sorular_tamam": false, "ipucu": "GUN_AY_YER_DEGISTI"}`

**Asistan:** Doğum tarihinizi ayın adıyla söyler misiniz? Örneğin on beş Mart gibi.

**Müşteri:** Dokuz Nisan bin dokuz yüz yetmiş dokuz.

> [Servis] `KimlikDogrula` ← `{"musteri_no": "FB-240402", "soru": "DOGUM_TARIHI", "cevap": "09.04.1979"}` → `{"basarili": true, "dogrulandi": true, "kalan_hak": 3, "tum_sorular_tamam": false}`

**Asistan:** Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?

**Müşteri:** Dokuz bir iki yedi.

> [Servis] `KimlikDogrula` ← `{"musteri_no": "FB-240402", "soru": "TCKN_SON4", "cevap": "9127"}` → `{"basarili": true, "dogrulandi": true, "kalan_hak": 3, "tum_sorular_tamam": true}`

> [Servis] `EkstreBorcSorgula` ← `{"musteri_no": "FB-240402"}` → `{"basarili": true, "kartlar": [{"kart_id": "KRT-240402-01", "urun": "KREDI_KARTI", "kart_son4": "3376", "ekstre_borcu": 2315.6, "asgari_odeme_tutari": 926.24, "son_odeme_tarihi": "2026-10-15", "gecikme_gun_sayisi": 7}]}`

**Asistan:** Teşekkür ederim Can Bey. Freya Bank tahsilat biriminden arıyorum. 3376 ile biten kredi kartınızın ekstre borcu 2.315,60 TL; son ödeme tarihi 15 Ekim idi ve ödeme 7 gündür gecikmede. Bu ödemeyi bugün yapabilir misiniz?

**Müşteri:** Ben onu dün internet bankacılığından ödedim ama.

**Asistan:** Ödemelerin sisteme yansıması bir iş günü sürebilir. Bilginizi not alıyorum.

> [Servis] `NotEkle` ← `{"musteri_no": "FB-240402", "kart_id": "KRT-240402-01", "not_tipi": "ODENDI_BEYANI", "aciklama": "Müşteri ekstre borcunu 21.10.2026 tarihinde internet bankacılığından ödediğini belirtti."}` → `{"basarili": true, "not_no": "NT-3001"}`

**Müşteri:** Tamam.

**Asistan:** Zaman ayırdığınız için teşekkür ederim, iyi günler dilerim.

> [Servis] `GorusmeKapat` ← `{"musteri_no": "FB-240402", "sonuc_kodu": "ODEME_YAPILMIS"}` → `{"basarili": true}`
