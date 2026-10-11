# Soru – Cevap

Ekiplerin hazırlık sırasında sorduğu sorular ve operasyon ekibinin cevapları.

**S1. Arife günü (ör. 28 Ekim 2026) ödeme sözü tarihi olabilir mi?**

C: Evet. Arife iş günüdür ve iş günü sayımına girer. Yalnızca geri arama 09:00–12:30 ile sınırlıdır.

**S2. Son tarih sayılırken bugün dahil mi?**

C: Hayır. Saymaya yarından başlanır. Örneğin Çarşamba 21 Ekim 2026'da geç bantta son tarih 3. iş günü olan 26 Ekim Pazartesi'dir (2 Kasım 2026 öncesi aramalar için).

**S3. Ekstre borcu müşterinin yaptığı kısmi ödemeleri içeriyor mu?**

C: `EkstreBorcSorgula` servisinin döndürdüğü `ekstre_borcu` güncel ödenmemiş tutardır. Asistan kendisi hesap yapmaz.

**S4. Müşteri tutarı yuvarlak söylerse (ör. 'beş bin üç yüz elli') kuruşlar ne olacak?**

C: Tutar ekstre borcuna eşitse tamamı kabul edilir. Asgari ile tamamı arasında herhangi bir tutar da kabul edilir; servise iki ondalıkla gönderilir.

**S5. Müşteri 'maaşım ayın 15'inde yatıyor' derse?**

C: Bu kesin bir gündür (ayın 15'i). Bölüm 7'ye göre kontrol edin: iş günü değilse sonraki iş günü, son tarihten sonraysa son tarih önerilir.

**S6. Müşteri 'haftaya' derse?**

C: Belirsiz dönemdir. Kesin günü bir kez sorun; yine gün söylemezse son tarihi önerin.

**S7. Müşteri kimlik sorularından önce borcun ne olduğunu sorarsa?**

C: Konuyu söylemeyin; soruların hesabını korumak için olduğunu bir kez açıklayın. Tekrar sorarsa veya cevap vermezse DOGRULANAMADI / CEVAP_VERMEDI ile kapatın.

**S8. İki kartı olan müşteri bir kart için 'ödedim' derse görüşme biter mi?**

C: Hayır. O kart için NotEkle ODENDI_BEYANI çağrılır ve diğer karta geçilir. Sonuç kodu BRIEF K47'ye göre seçilir.

**S9. Müşteri faiz oranını sorarsa?**

C: Asistanın bu bilgisi yoktur; bilgisi olmadığını söyler ve devam eder. Oran veya rakam uydurmaz.

**S10. Müşteri sözü kaydettikten sonra tarihi değiştirmek isterse?**

C: Kaydedilmiş söz aynı görüşmede değiştirilemez; mobil uygulamadan değiştirebileceği söylenir.

**S11. Asgari ödeme pilot uygulaması (asgarinin yarısı) hâlâ geçerli mi?**

C: Hayır. DUY-2026-028 30 Eylül 2026'da sona erdi; asgarinin altındaki tutarlar kaydedilmez.

**S12. Cumartesi günü söz alınabilir mi?**

C: Hayır. Cumartesi pilotu (DUY-2026-035) onaylanmadı; söz tarihi her zaman iş günü olmalıdır.

**S13. OdemeSozuKaydet E006 döndürürse tekrar denenir mi?**

C: Hayır. E006 o kart için bu görüşmede zaten söz kaydedildiği anlamına gelir; ikinci kayıt yapılmaz.
