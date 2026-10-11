# Örnek Konuşma 1 — Ekstre borcunun tamamı bugün

- Arama zamanı (`now`): `2026-10-21T10:30` (21 Ekim 2026 Çarşamba, saat 10:30)
- Müşteri: `FB-240117` — Ayşe Yılmaz (Hanım)
- Çağrı değişkenleri: `{"musteri_no": "FB-240117", "ad": "Ayşe", "soyad": "Yılmaz", "hitap": "Hanım", "now": "2026-10-21T10:30"}`

Servis çağrıları `[Servis]` satırlarında, gönderilen gövde ve gelen cevapla gösterilmiştir.

**Asistan:** Merhaba, ben Freya Bank'ın dijital asistanıyım. Bu görüşme kalite amacıyla kayıt altına alınmaktadır. Ayşe Yılmaz ile mi görüşüyorum?

**Müşteri:** Evet, benim.

**Asistan:** Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?

**Müşteri:** On dört Şubat seksen altı.

> [Servis] `KimlikDogrula` ← `{"musteri_no": "FB-240117", "soru": "DOGUM_TARIHI", "cevap": "14.02.1986"}` → `{"basarili": true, "dogrulandi": true, "kalan_hak": 3, "tum_sorular_tamam": false}`

**Asistan:** Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?

**Müşteri:** Üç sıfır beş sekiz.

> [Servis] `KimlikDogrula` ← `{"musteri_no": "FB-240117", "soru": "TCKN_SON4", "cevap": "3058"}` → `{"basarili": true, "dogrulandi": true, "kalan_hak": 3, "tum_sorular_tamam": true}`

> [Servis] `EkstreBorcSorgula` ← `{"musteri_no": "FB-240117"}` → `{"basarili": true, "kartlar": [{"kart_id": "KRT-240117-01", "urun": "KREDI_KARTI", "kart_son4": "7319", "ekstre_borcu": 8450.75, "asgari_odeme_tutari": 3380.3, "son_odeme_tarihi": "2026-10-15", "gecikme_gun_sayisi": 6}]}`

**Asistan:** Teşekkür ederim Ayşe Hanım. Freya Bank tahsilat biriminden arıyorum. 7319 ile biten kredi kartınızın ekstre borcu 8.450,75 TL; son ödeme tarihi 15 Ekim idi ve ödeme 6 gündür gecikmede. Bu ödemeyi bugün yapabilir misiniz?

**Müşteri:** Evet, bugün tamamını yatırırım.

**Asistan:** Özetliyorum: 7319 ile biten kredi kartınız için 8.450,75 TL, ödeme tarihi 21 Ekim 2026 Çarşamba. Onaylıyor musunuz?

**Müşteri:** Evet, onaylıyorum.

> [Servis] `OdemeSozuKaydet` ← `{"musteri_no": "FB-240117", "kart_id": "KRT-240117-01", "tutar": 8450.75, "odeme_tarihi": "2026-10-21", "soz_tipi": "TAMAMI"}` → `{"basarili": true, "soz_no": "SZ-1001"}`

**Asistan:** Ödeme sözünüz kaydedildi. Bu ödeme sözünü onaylayan bir SMS alacaksınız. Başka bir sorunuz var mı?

**Müşteri:** Yok, teşekkürler.

**Asistan:** Zaman ayırdığınız için teşekkür ederim, iyi günler dilerim.

> [Servis] `GorusmeKapat` ← `{"musteri_no": "FB-240117", "sonuc_kodu": "SOZ_ALINDI"}` → `{"basarili": true}`
