# Freya Bank — Ekstre Borcu Hattı Servis Sözleşmesi

Sürüm 2.3 — Test ortamı. Belge sahibi: Kartlı Ödemeler Entegrasyon Ekibi.

## 1. Genel

- Bütün servisler HTTPS üzerinden POST ile çağrılır; gövde ve cevap UTF-8 JSON'dur.
- Adresler ortamın taban adresine göredir (ör. <taban>/kimlik/dogrula). Test ortamının taban adresi ayrıca bildirilir.
- Her cevapta basarili alanı vardır. İş hatalarında HTTP 200 ile basarili: false ve hata_kodu döner. Sistem hatasında HTTP 500 ve hata_kodu: E500 döner.
- Servisler BRIEF'teki iş kurallarını (tatil, son tarih, tutar aralığı) denetlemez.
- Kimlik doğrulama, müşteri ve görüşme bazında tutulur. Bir görüşmede yapılan bütün çağrılar kayıt defterine (ledger) yazılır ve değerlendirmede bu kayıt kullanılır.
## 2. Servis listesi

| No | Servis | Adres | Ne yapar |
|---|---|---|---|
| 1 | KimlikDogrula | POST /kimlik/dogrula | Bir güvenlik cevabını kontrol eder. Toplam üç yanlış cevap kontrolü bitirir. |
| 2 | EkstreBorcSorgula | POST /ekstre/borc-sorgula | Müşterinin gecikmiş kredi kartı ekstre borçları. İki güvenlik sorusu geçilmeden E002 döner. |
| 3 | OdemeSozuKaydet | POST /odeme-sozu/kaydet | Bir kart için ödeme sözünü kaydeder. Kart başına görüşmede bir söz; ikincisi E006 ile reddedilir. Servis tatil veya son tarih kontrolü yapmaz. |
| 4 | GeriAramaPlanla | POST /geri-arama/planla | Müşteriye ulaşılamadığında geri arama randevusu. |
| 5 | CagriAktar | POST /cagri/aktar | Görüşmeyi bir ekibe aktarır. |
| 6 | NotEkle | POST /not/ekle | Müşteri kaydına not ekler. |
| 7 | GorusmeKapat | POST /gorusme/kapat | Görüşmeyi sonuç koduyla kapatır. Her görüşmede bir kez ve en son çağrılır. |

## 3. KimlikDogrula

**Adres:** POST /kimlik/dogrula

Bir güvenlik cevabını kontrol eder. Toplam üç yanlış cevap kontrolü bitirir.

### İstek alanları

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| musteri_no | string | Evet | Çağrı değişkeni musteri_no. |
| soru | string (enum) | Evet | DOGUM_TARIHI veya TCKN_SON4. |
| cevap | string | Evet | DOGUM_TARIHI için GG.AA.YYYY (ör. 14.02.1986). TCKN_SON4 için dört rakam (baştaki sıfırlar korunur, ör. 0285). Okunamayan değer E004 ile reddedilir ve yanlış sayılmaz. |

### Cevap alanları

| Alan | Tip | Açıklama |
|---|---|---|
| basarili | boolean | İşlem yapıldıysa true. |
| hata_kodu | string | basarili false ise hata kodu (bölüm 11). |
| dogrulandi | boolean | Bu cevap doğru mu. |
| kalan_hak | integer | Kalan yanlış cevap hakkı (başlangıçta 3). |
| tum_sorular_tamam | boolean | İki soru da doğrulandıysa true. |
| ipucu | string (enum) | GUN_AY_YER_DEGISTI: doğum tarihinde gün ile ay yer değiştirmiş. Yanlış sayılmaz. |

## 4. EkstreBorcSorgula

**Adres:** POST /ekstre/borc-sorgula

Müşterinin gecikmiş kredi kartı ekstre borçları. İki güvenlik sorusu geçilmeden E002 döner.

### İstek alanları

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| musteri_no | string | Evet | Çağrı değişkeni musteri_no. |

### Cevap alanları

| Alan | Tip | Açıklama |
|---|---|---|
| basarili | boolean | İşlem yapıldıysa true. |
| hata_kodu | string | Bölüm 11. |
| kartlar | dizi | Gecikmiş kartlar. Her eleman aşağıdaki alanları taşır. |
| kartlar[].kart_id | string | Kartın servis kimliği (OdemeSozuKaydet ve NotEkle için). |
| kartlar[].urun | string (enum) | KREDI_KARTI. |
| kartlar[].kart_son4 | string | Kart numarasının son dört hanesi (müşteriye söylenir). |
| kartlar[].ekstre_borcu | number | Ödenmemiş ekstre borcu, TL, iki ondalık. |
| kartlar[].asgari_odeme_tutari | number | Asgari ödeme tutarı, TL. |
| kartlar[].son_odeme_tarihi | string (date) | Ekstrenin son ödeme tarihi, YYYY-AA-GG. |
| kartlar[].gecikme_gun_sayisi | integer | Son ödeme tarihinden bu yana geçen gün sayısı. |

## 5. OdemeSozuKaydet

**Adres:** POST /odeme-sozu/kaydet

Bir kart için ödeme sözünü kaydeder. Kart başına görüşmede bir söz; ikincisi E006 ile reddedilir. Servis tatil veya son tarih kontrolü yapmaz.

### İstek alanları

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| musteri_no | string | Evet | Çağrı değişkeni musteri_no. |
| kart_id | string | Evet | EkstreBorcSorgula'dan gelen kart_id. |
| tutar | number | Evet | TL, en fazla iki ondalık, sıfırdan büyük. |
| odeme_tarihi | string (date) | Evet | YYYY-AA-GG. |
| soz_tipi | string (enum) | Evet | TAMAMI, ASGARI veya KISMI (BRIEF K30). |

### Cevap alanları

| Alan | Tip | Açıklama |
|---|---|---|
| basarili | boolean | Söz kaydedildiyse true. |
| hata_kodu | string | Bölüm 11. |
| soz_no | string | Kaydedilen sözün numarası. |

## 6. GeriAramaPlanla

**Adres:** POST /geri-arama/planla

Müşteriye ulaşılamadığında geri arama randevusu.

### İstek alanları

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| musteri_no | string | Evet | Çağrı değişkeni musteri_no. |
| tarih | string (date) | Evet | YYYY-AA-GG. |
| saat | string | Evet | SS:DD, 24 saat (ör. 18:30). |

### Cevap alanları

| Alan | Tip | Açıklama |
|---|---|---|
| basarili | boolean | Randevu oluşturulduysa true. |
| hata_kodu | string | Bölüm 11. |
| randevu_no | string | Randevu numarası. |

## 7. CagriAktar

**Adres:** POST /cagri/aktar

Görüşmeyi bir ekibe aktarır.

### İstek alanları

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| musteri_no | string | Evet | Çağrı değişkeni musteri_no. |
| kuyruk | string (enum) | Evet | FINANSAL_DESTEK, YAPILANDIRMA veya MUSTERI_TEMSILCISI. |

### Cevap alanları

| Alan | Tip | Açıklama |
|---|---|---|
| basarili | boolean | Aktarım yapıldıysa true. |
| hata_kodu | string | Bölüm 11. |

## 8. NotEkle

**Adres:** POST /not/ekle

Müşteri kaydına not ekler.

### İstek alanları

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| musteri_no | string | Evet | Çağrı değişkeni musteri_no. |
| kart_id | string | Hayır | Notun ilgili olduğu kart. |
| not_tipi | string (enum) | Evet | ODENDI_BEYANI veya ITIRAZ. |
| aciklama | string | Evet | Kısa açıklama, en fazla 500 karakter. |

### Cevap alanları

| Alan | Tip | Açıklama |
|---|---|---|
| basarili | boolean | Not eklendiyse true. |
| hata_kodu | string | Bölüm 11. |
| not_no | string | Not numarası. |

## 9. GorusmeKapat

**Adres:** POST /gorusme/kapat

Görüşmeyi sonuç koduyla kapatır. Her görüşmede bir kez ve en son çağrılır.

### İstek alanları

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| musteri_no | string | Evet | Çağrı değişkeni musteri_no. |
| sonuc_kodu | string (enum) | Evet | Bölüm 10. |
| gerekce_kodu | string (enum) | Hayır | Bölüm 10; tabloda gerekçe yoksa gönderilmez. |

### Cevap alanları

| Alan | Tip | Açıklama |
|---|---|---|
| basarili | boolean | Görüşme kapatıldıysa true. |
| hata_kodu | string | Bölüm 11. |

## 10. Kapanış tablosu (sonuç ve gerekçe kodları)

GorusmeKapat yalnızca bu tablodaki çiftlerle çağrılır. Gerekçesi olmayan sonuçlarda gerekce_kodu gönderilmez.

| sonuc_kodu | gerekce_kodu | Ne zaman |
|---|---|---|
| SOZ_ALINDI | — (gönderilmez) | En az bir kart için ödeme sözü kaydedildi. |
| ODEME_YAPILMIS | — (gönderilmez) | Müşteri gecikmiş ekstre borcunu zaten ödediğini söyledi (tüm kartlar). |
| AKTARILDI | FINANSAL_DESTEK | Zor durumdaki müşteri Finansal Destek Ekibine aktarıldı. |
| AKTARILDI | YAPILANDIRMA | Yapılandırma / taksitlendirme isteği; Yapılandırma Ekibine aktarıldı. |
| AKTARILDI | TEMSILCI | Müşteri ısrarla bir temsilci istedi; aktarıldı. |
| SOZ_ALINAMADI | REDDETTI | İkna denemeleri bitti veya müşteri konuşmak istemedi. |
| SOZ_ALINAMADI | ZOR_DURUM | Zor durum; müşteri aktarımı kabul etmedi. |
| SOZ_ALINAMADI | ITIRAZ | Müşteri borca / harcamaya itiraz etti. |
| SOZ_ALINAMADI | SISTEM_HATASI | OdemeSozuKaydet iki denemede de başarısız oldu. |
| DOGRULANAMADI | HATALI_CEVAP | Toplam üç yanlış cevap. |
| DOGRULANAMADI | CEVAP_VERMEDI | Müşteri güvenlik sorularını cevaplamak istemedi. |
| ULASILAMADI | GERI_ARAMA | Telefonu başkası açtı; geri arama planlandı. |
| ULASILAMADI | GERI_ARAMA_YOK | Telefonu başkası açtı; uygun saat bulunamadı. |
| ULASILAMADI | YANLIS_NUMARA | Numara müşteriye ait değil. |
| ULASILAMADI | VEFAT | Müşterinin vefat ettiği söylendi. |
| ULASILAMADI | BELIRSIZ | İki sorudan sonra hattaki kişi teyit edilemedi. |

Kuyruk ile gerekçe kodu aynı değildir: MUSTERI_TEMSILCISI kuyruğuna aktarılan görüşme TEMSILCI gerekçesiyle kapatılır.

Kullanımdan kalkan kodlar (gönderilmez): SESLI_MESAJ, HUKUKI_TAKIP.

## 11. Hata kodları

| Kod | Anlamı | Tekrar denenir mi |
|---|---|---|
| E001 | Müşteri bulunamadı. | Hayır |
| E002 | Kimlik doğrulaması tamamlanmadı (EkstreBorcSorgula / OdemeSozuKaydet erken çağrıldı). | Hayır |
| E003 | Doğrulama hakkı bitti (üç yanlış cevap). | Hayır |
| E004 | Geçersiz biçim (ör. okunamayan tarih). Yanlış cevap sayılmaz. | Doğru biçimle |
| E005 | Kart bulunamadı veya müşteriye ait değil. | Hayır |
| E006 | Bu kart için bu görüşmede zaten söz kaydedildi. | Hayır |
| E007 | Geçersiz değer (izin verilen değerlerin dışında, tutar ≤ 0, geçmiş tarih). | Doğru değerle |
| E500 | Sistem hatası. Hiçbir şey kaydedilmedi. HTTP 500 ile döner. | Evet (BRIEF K39: bir kez) |

## 12. Örnek istek ve cevap

POST /kimlik/dogrula  {"musteri_no": "FB-000001", "soru": "DOGUM_TARIHI", "cevap": "01.01.1980"}

200  {"basarili": true, "dogrulandi": false, "kalan_hak": 2, "tum_sorular_tamam": false}

POST /odeme-sozu/kaydet  {"musteri_no": "FB-000001", "kart_id": "KRT-000001-01", "tutar": 1000.0, "odeme_tarihi": "2026-01-02", "soz_tipi": "KISMI"}

500  {"basarili": false, "hata_kodu": "E500"}

