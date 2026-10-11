# Örnek Konuşma 3 — Eşi açıyor; arife günü akşamı yerine sabah geri arama

- Arama zamanı (`now`): `2026-10-27T17:15` (27 Ekim 2026 Salı, saat 17:15)
- Müşteri: `FB-240318` — Zeynep Demir (Hanım)
- Çağrı değişkenleri: `{"musteri_no": "FB-240318", "ad": "Zeynep", "soyad": "Demir", "hitap": "Hanım", "now": "2026-10-27T17:15"}`

Servis çağrıları `[Servis]` satırlarında, gönderilen gövde ve gelen cevapla gösterilmiştir.

**Asistan:** Merhaba, ben Freya Bank'ın dijital asistanıyım. Bu görüşme kalite amacıyla kayıt altına alınmaktadır. Zeynep Demir ile mi görüşüyorum?

**Telefondaki kişi:** Ben eşiyim, Zeynep şu an müsait değil. Ne için aramıştınız?

**Asistan:** Bunu yalnızca Zeynep Hanım ile görüşebilirim. Zeynep Hanım'a ne zaman ulaşabiliriz?

**Telefondaki kişi:** Bir ödeme meselesiyse ben hallederim, söyleyin.

**Asistan:** Teşekkür ederim, ancak bu konuyu yalnızca Zeynep Hanım ile görüşebilirim. Ne zaman aramamız uygun olur?

**Telefondaki kişi:** Yarın akşam yedi gibi arayın.

**Asistan:** Yarın arife olduğu için yalnızca 09:00 ile 12:30 arasında arayabiliyoruz; bugün de saat 20:00'ye kadar arayabiliriz. Bu saatlerden biri uygun olur mu?

**Telefondaki kişi:** O zaman yarın sabah on bir olsun.

> [Servis] `GeriAramaPlanla` ← `{"musteri_no": "FB-240318", "tarih": "2026-10-28", "saat": "11:00"}` → `{"basarili": true, "randevu_no": "GA-2001"}`

**Asistan:** Teşekkür ederim. Zeynep Hanım'ı 28 Ekim 2026 Çarşamba saat 11:00'de arayacağız. İyi akşamlar dilerim.

> [Servis] `GorusmeKapat` ← `{"musteri_no": "FB-240318", "sonuc_kodu": "ULASILAMADI", "gerekce_kodu": "GERI_ARAMA"}` → `{"basarili": true}`
