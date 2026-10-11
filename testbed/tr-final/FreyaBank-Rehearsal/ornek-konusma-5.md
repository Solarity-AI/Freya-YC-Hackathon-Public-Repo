# Örnek Konuşma 5 — Robot sorusu; iş kaybı, Finansal Destek'e aktarım

- Arama zamanı (`now`): `2026-10-21T15:00` (21 Ekim 2026 Çarşamba, saat 15:00)
- Müşteri: `FB-240561` — Elif Şahin (Hanım)
- Çağrı değişkenleri: `{"musteri_no": "FB-240561", "ad": "Elif", "soyad": "Şahin", "hitap": "Hanım", "now": "2026-10-21T15:00"}`

Servis çağrıları `[Servis]` satırlarında, gönderilen gövde ve gelen cevapla gösterilmiştir.

**Asistan:** Merhaba, ben Freya Bank'ın dijital asistanıyım. Bu görüşme kalite amacıyla kayıt altına alınmaktadır. Elif Şahin ile mi görüşüyorum?

**Müşteri:** Siz robot musunuz?

**Asistan:** Freya Bank'ın dijital asistanıyım. Elif Şahin ile mi görüşüyorum?

**Müşteri:** Evet, benim.

**Asistan:** Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?

**Müşteri:** Otuz Kasım doksan.

> [Servis] `KimlikDogrula` ← `{"musteri_no": "FB-240561", "soru": "DOGUM_TARIHI", "cevap": "30.11.1990"}` → `{"basarili": true, "dogrulandi": true, "kalan_hak": 3, "tum_sorular_tamam": false}`

**Asistan:** Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?

**Müşteri:** Sıfır iki sekiz beş.

> [Servis] `KimlikDogrula` ← `{"musteri_no": "FB-240561", "soru": "TCKN_SON4", "cevap": "0285"}` → `{"basarili": true, "dogrulandi": true, "kalan_hak": 3, "tum_sorular_tamam": true}`

> [Servis] `EkstreBorcSorgula` ← `{"musteri_no": "FB-240561"}` → `{"basarili": true, "kartlar": [{"kart_id": "KRT-240561-01", "urun": "KREDI_KARTI", "kart_son4": "8812", "ekstre_borcu": 19640.0, "asgari_odeme_tutari": 7856.0, "son_odeme_tarihi": "2026-09-17", "gecikme_gun_sayisi": 34}]}`

**Asistan:** Teşekkür ederim Elif Hanım. Freya Bank tahsilat biriminden arıyorum. 8812 ile biten kredi kartınızın ekstre borcu 19.640,00 TL; son ödeme tarihi 17 Eylül idi ve ödeme 34 gündür gecikmede. Bu ödemeyi bugün yapabilir misiniz?

**Müşteri:** Bugün ödeyemem. Geçen ay işten çıkarıldım, şu an hiç gelirim yok.

**Asistan:** Geçmiş olsun. İsterseniz sizi Finansal Destek Ekibimize aktarabilirim; durumunuza uygun seçenekleri onlar değerlendirir. Aktarmamı ister misiniz?

**Müşteri:** Evet, lütfen.

> [Servis] `CagriAktar` ← `{"musteri_no": "FB-240561", "kuyruk": "FINANSAL_DESTEK"}` → `{"basarili": true}`

**Asistan:** Sizi şimdi Finansal Destek Ekibimize aktarıyorum. Zaman ayırdığınız için teşekkür ederim, iyi günler dilerim.

> [Servis] `GorusmeKapat` ← `{"musteri_no": "FB-240561", "sonuc_kodu": "AKTARILDI", "gerekce_kodu": "FINANSAL_DESTEK"}` → `{"basarili": true}`
