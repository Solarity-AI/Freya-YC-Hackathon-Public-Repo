# Freya Bank — Ekstre Borcu Hattı: belge klasörü

Bu klasör, Freya Bank kredi kartı ekstre borcu hattında çalışacak dijital asistan için hazırlanan belgeleri içerir.
Tüm veriler kurgusaldır.

| Dosya | Ne olduğu |
|---|---|
| `BRIEF.md` | Asistanın kuralları. Önce bunu okuyun. |
| `README.md` | Bu dosya: klasördeki belgelerin listesi. |
| `analiz.docx` | Ekstre borcu hattının süreç analizi (iş birimi). Arka plan ve gerekçeler; bağlayıcı kural değildir. |
| `akis.drawio` | Görüşme akış şeması (draw.io / diagrams.net dosyası). |
| `duyurular.pdf` | Operasyon duyuruları. Yürürlük tarihi gelen duyuru BRIEF'teki kuralı değiştirir. |
| `servis-sozlesmesi.docx` | Asistanın çağırdığı banka servisleri: alanlar, değerler, hata kodları, kapanış tablosu. |
| `test-musterileri.xlsx` | Test ortamındaki müşteriler ve kartları (mock servis bu verilerle çalışır). |
| `soru-cevap.md` | Ekiplerden gelen sorular ve cevapları. |
| `ornek-konusma-1.md` | Örnek konuşma: kuralların nasıl uygulandığını gösterir, yeni kural koymaz. |
| `ornek-konusma-2.md` | Örnek konuşma: kuralların nasıl uygulandığını gösterir, yeni kural koymaz. |
| `ornek-konusma-3.md` | Örnek konuşma: kuralların nasıl uygulandığını gösterir, yeni kural koymaz. |
| `ornek-konusma-4.md` | Örnek konuşma: kuralların nasıl uygulandığını gösterir, yeni kural koymaz. |
| `ornek-konusma-5.md` | Örnek konuşma: kuralların nasıl uygulandığını gösterir, yeni kural koymaz. |
| `ornek-konusma-6.md` | Örnek konuşma: kuralların nasıl uygulandığını gösterir, yeni kural koymaz. |

## Öncelik

1. `duyurular.pdf` içindeki bir duyuru, yürürlük tarihinden itibaren yapılan aramalarda BRIEF'teki ilgili kuralı
   değiştirir. Hangi kuralın geçerli olduğuna **aramanın tarihi** (`now`) karar verir. Onaylanmayan veya süresi geçen
   duyurular uygulanmaz.
2. `BRIEF.md` diğer bütün belgelerden önce gelir.
3. Servis adları, alanlar ve kodlar için `servis-sozlesmesi.docx` esastır.
4. `analiz.docx`, `akis.drawio`, `soru-cevap.md` ve örnek konuşmalar açıklayıcıdır; BRIEF ile çelişirlerse BRIEF geçerlidir.

## Test ortamı

Servisler test ortamında, `test-musterileri.xlsx` içindeki müşterilerle çalışan bir mock üzerinden çağrılır. Mock
iş kurallarını denetlemez (ör. tatil gününe söz kaydını reddetmez); kuralları uygulamak asistanın işidir.
