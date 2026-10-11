# Örnek Konuşma 6 — Dolandırıcılık sorusu; iki kart: biri söz (son tarih), biri itiraz

- Arama zamanı (`now`): `2026-11-03T10:00` (3 Kasım 2026 Salı, saat 10:00)
- Müşteri: `FB-240699` — Burak Arslan (Bey)
- Çağrı değişkenleri: `{"musteri_no": "FB-240699", "ad": "Burak", "soyad": "Arslan", "hitap": "Bey", "now": "2026-11-03T10:00"}`

Servis çağrıları `[Servis]` satırlarında, gönderilen gövde ve gelen cevapla gösterilmiştir.

**Asistan:** Merhaba, ben Freya Bank'ın dijital asistanıyım. Bu görüşme kalite amacıyla kayıt altına alınmaktadır. Burak Arslan ile mi görüşüyorum?

**Müşteri:** Bu bir dolandırıcılık olmasın?

**Asistan:** Bu aramayı Freya Bank müşteri hizmetleri numarasını arayarak doğrulayabilirsiniz. Burak Arslan ile mi görüşüyorum?

**Müşteri:** Evet benim.

**Asistan:** Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?

**Müşteri:** İki altı seksen üç.

> [Servis] `KimlikDogrula` ← `{"musteri_no": "FB-240699", "soru": "DOGUM_TARIHI", "cevap": "02.06.1983"}` → `{"basarili": true, "dogrulandi": true, "kalan_hak": 3, "tum_sorular_tamam": false}`

**Asistan:** Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?

**Müşteri:** Yedi yedi beş bir.

> [Servis] `KimlikDogrula` ← `{"musteri_no": "FB-240699", "soru": "TCKN_SON4", "cevap": "7751"}` → `{"basarili": true, "dogrulandi": true, "kalan_hak": 3, "tum_sorular_tamam": true}`

> [Servis] `EkstreBorcSorgula` ← `{"musteri_no": "FB-240699"}` → `{"basarili": true, "kartlar": [{"kart_id": "KRT-240699-01", "urun": "KREDI_KARTI", "kart_son4": "5502", "ekstre_borcu": 14200.0, "asgari_odeme_tutari": 5680.0, "son_odeme_tarihi": "2026-09-24", "gecikme_gun_sayisi": 40}, {"kart_id": "KRT-240699-02", "urun": "KREDI_KARTI", "kart_son4": "1187", "ekstre_borcu": 3120.9, "asgari_odeme_tutari": 1248.36, "son_odeme_tarihi": "2026-10-26", "gecikme_gun_sayisi": 8}]}`

**Asistan:** Teşekkür ederim Burak Bey. Freya Bank tahsilat biriminden arıyorum. İki kredi kartınızda gecikme var; önce en çok geciken kartla başlayacağım. 5502 ile biten kredi kartınızın ekstre borcu 14.200,00 TL; son ödeme tarihi 24 Eylül idi ve ödeme 40 gündür gecikmede. Bu ödemeyi bugün yapabilir misiniz?

**Müşteri:** Bugün olmaz.

**Asistan:** 14.200,00 TL tutarın tamamını 5 Kasım 2026 Perşembe günü ödeyebilir misiniz?

**Müşteri:** Tamam, perşembe öderim.

**Asistan:** Özetliyorum: 5502 ile biten kredi kartınız için 14.200,00 TL, ödeme tarihi 5 Kasım 2026 Perşembe. Onaylıyor musunuz?

**Müşteri:** Evet, onaylıyorum.

> [Servis] `OdemeSozuKaydet` ← `{"musteri_no": "FB-240699", "kart_id": "KRT-240699-01", "tutar": 14200.0, "odeme_tarihi": "2026-11-05", "soz_tipi": "TAMAMI"}` → `{"basarili": true, "soz_no": "SZ-1006"}`

**Asistan:** Ödeme sözünüz kaydedildi. Bu ödeme sözünü onaylayan bir SMS alacaksınız. Bir de 1187 ile biten kredi kartınızın ekstre borcu 3.120,90 TL; son ödeme tarihi 26 Ekim idi ve ödeme 8 gündür gecikmede. Bu ödemeyi bugün yapabilir misiniz?

**Müşteri:** O karttaki harcamaları ben yapmadım, bankaya itiraz ettim zaten.

**Asistan:** Anlıyorum, itirazınızı not alıyorum.

> [Servis] `NotEkle` ← `{"musteri_no": "FB-240699", "kart_id": "KRT-240699-02", "not_tipi": "ITIRAZ", "aciklama": "Müşteri 1187 ile biten karttaki harcamaları kendisinin yapmadığını ve itiraz ettiğini söyledi."}` → `{"basarili": true, "not_no": "NT-3006"}`

**Asistan:** Zaman ayırdığınız için teşekkür ederim, iyi günler dilerim.

> [Servis] `GorusmeKapat` ← `{"musteri_no": "FB-240699", "sonuc_kodu": "SOZ_ALINDI"}` → `{"basarili": true}`
