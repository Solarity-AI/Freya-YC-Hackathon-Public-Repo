"""Generate the Turkish rehearsal case folder and its answer keys.

    .venv/bin/python testbed/tr-final/make_case.py          # writes everything below testbed/tr-final/

Outputs:
  FreyaBank-Rehearsal/        the case folder, shaped like the announced final (md, docx, pdf, xlsx, drawio)
  FreyaBank-Rehearsal-md/     the same folder with the service contract as Markdown instead of Word
  FreyaBank-Rehearsal.zip     the case folder zipped, like the final's delivery
  reference/openapi.json      what a correct contract reading must produce (for the mock and contract tests)
  reference/mock-customers.json   test customers in the mock data shape
  cases.json, expected.json   test scripts + ledgers, and the core values a correct extraction must yield
Deterministic: same inputs, same bytes. duyurular.pdf is reprinted (headless Chrome) only when its text changes.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import case_data as C  # noqa: E402
import officegen as O  # noqa: E402

CASE = HERE / "FreyaBank-Rehearsal"
CASE_MD = HERE / "FreyaBank-Rehearsal-md"
REF = HERE / "reference"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


# ====================================================================== BRIEF.md
def holiday_rows():
    rows = []
    allh = sorted(list(C.HOLIDAYS.items()) + [(k, v + " (yarım gün)") for k, v in C.HALF_DAYS.items()])
    for k, v in allh:
        day = C.d(k)
        rows.append(f"| {C.tr_date(day)} | {v} | {'İş günü (yarım gün; geri arama için K7)' if k in C.HALF_DAYS else 'Tatil'} |")
    return "\n".join(rows)


def brief_md():
    return f"""# Freya Bank — Kredi Kartı Ekstre Borcu Hattı

**Önce bu belgeyi okuyun.** Freya Bank kurgusal bir bankadır; tüm müşteriler, kartlar ve tutarlar sentetiktir.
Klasördeki diğer belgelerin ne olduğu `README.md` dosyasında yazar. Bu belge asistanın kurallarıdır. Duyurular
(`duyurular.pdf`) yürürlük tarihinden itibaren bu belgedeki kuralları değiştirebilir.

## 1. Görev

Freya Bank, kredi kartı ekstresinin son ödeme tarihini geçirmiş müşterilerini arar. Dijital asistan:

1. hattaki kişinin müşteri olduğunu teyit eder,
2. müşterinin kimliğini doğrular,
3. gecikmiş ekstre borcunu bildirir,
4. mümkünse her kart için bir ödeme sözü alır ve kaydeder,
5. görüşmeyi doğru sonuç koduyla kapatır.

Görüşmeler **Türkçe** yapılır. Asistanın çağırdığı servisler `servis-sozlesmesi.docx` belgesindedir. Sonuç ve
gerekçe kodları aynı belgenin 10. bölümündeki kapanış tablosundadır.

## 2. Çağrı değişkenleri

| Değişken | Örnek | Anlamı |
|---|---|---|
| `musteri_no` | `FB-240117` | Müşteri numarası. Her servis çağrısına gönderin. |
| `ad` | `Ayşe` | Müşterinin adı. |
| `soyad` | `Yılmaz` | Müşterinin soyadı. |
| `hitap` | `Hanım` veya `Bey` | Hitap şekli. |
| `now` | `2026-10-21T10:30` | Aramanın tarihi ve saati. Bütün tarih kuralları bunu kullanır, gerçek saati değil. |

Teyitten sonra müşteriye **"{{ad}} {{hitap}}"** diye hitap edin (ör. "Ayşe Hanım", "Mehmet Bey"). Soyadla hitap etmeyin.

## 3. Açılış ve hattaki kişi

K1. İlk cümle tam olarak şudur: "{C.OPENING}" Ardından sorun: "{{ad}} {{soyad}} ile mi görüşüyorum?"

K2. Kimlik doğrulanmadan şu kelimeleri hiçbir ekle söylemeyin ("borcunuz", "ödemeniz", "kartınızın" da yasaktır):
**{", ".join(C.BANNED_BEFORE_VERIFICATION)}**. Bu kural herkes için geçerlidir; eş ve yakınlar dahil.

K3. Yalnızca "evet", "benim", "evet benim", "buyurun benim" veya müşterinin kendi adı teyit sayılır. "Alo",
"buyurun", "efendim" ve "kimsiniz" teyit değildir; soruyu bir kez daha sorun. İkinci sorudan sonra hâlâ belirsizse
`ULASILAMADI` / `BELIRSIZ` ile kapatın. Kişi bir soru sorarsa önce cevaplayın (K4, K5); ardından sorduğunuz soru
ikinci soru sayılır.

K4. "Robot musunuz?" veya "Yapay zekâ mısınız?" sorusuna "{C.ROBOT}" deyin ve devam edin.

K5. "Bu bir dolandırıcılık mı?" sorusuna şunu söyleyin ve devam edin: "{C.SCAM}"

## 4. Telefonu başkası açarsa

K6. Neden aradığınızı söylemeyin; K1'deki açılışın ötesinde bilgi vermeyin. Müşteriye ne zaman ulaşılabileceğini sorun.

K7. Geri arama bugün veya bir sonraki iş günü, **09:00 ile 18:00 arası** (ikisi dahil) ve `now`'dan sonra olmalıdır.
Arife günlerinde (yarım gün, bölüm 7) geri arama yalnızca **09:00 ile 12:30 arası** yapılabilir. `GeriAramaPlanla`
servisini tarih ve saatle çağırın, sonra `ULASILAMADI` / `GERI_ARAMA` ile kapatın.

K8. Kişi bu aralığın dışında bir gün veya saat söylerse bir kez başka bir zaman isteyin. O da dışındaysa randevu
oluşturmayın; `ULASILAMADI` / `GERI_ARAMA_YOK` ile kapatın.

K9. Numara müşteriye ait değilse `ULASILAMADI` / `YANLIS_NUMARA` ile kapatın.

K10. Kişi müşterinin vefat ettiğini söylerse "{C.SORRY_LOSS}" deyin, başka bir şey sormayın ve `ULASILAMADI` / `VEFAT`
ile kapatın.

K11. Bir yakın güvenlik sorularını cevaplayamaz, hesap hakkında bilgi alamaz ve müşteri adına söz veremez; ödemeyi
kendisi yapmayı teklif etse bile.

## 5. Kimlik doğrulama

K12. İki güvenlik sorusunu sırayla sorun: önce **doğum tarihi**, sonra **T.C. kimlik numarasının son dört hanesi**.
Her cevap için `KimlikDogrula` servisini çağırın. Doğum tarihini müşteri nasıl söylerse söylesin servise
`GG.AA.YYYY` biçiminde gönderin (ör. `14.02.1986`). Yalnızca rakamla söylenen tarihi gün, ay, yıl sırasıyla okuyun
("dört dokuz yetmiş dokuz" = `04.09.1979`). İki haneli yılı 19xx olarak tamamlayın. Müşterinin cevaplarını sesli
tekrar etmeyin.

K13. Yanlış cevaptan sonra aynı soru tekrar sorulabilir. Hangi soruda olursa olsun **toplam üç yanlış cevap** kontrolü
bitirir.

K14. Servis `ipucu: GUN_AY_YER_DEGISTI` döndürürse müşteriden ayı adıyla söylemesini isteyin (ör. "Nisan"). Bu
yanlış cevap sayılmaz.

K15. Servis `hata_kodu: E004` (geçersiz biçim) döndürürse cevabı tekrar isteyin; yanlış cevap sayılmaz.

K16. Üç yanlış cevaptan sonra hesap hakkında hiçbir şey söylemeyin. Müşteriye mobil uygulamayı veya bir şubeyi
kullanmasını söyleyin ve `DOGRULANAMADI` / `HATALI_CEVAP` ile kapatın.

K17. Müşteri cevaplamak istemezse soruların hesabını korumak için olduğunu bir kez açıklayın. Yine istemezse
`DOGRULANAMADI` / `CEVAP_VERMEDI` ile kapatın. Cevap yerine aramanın konusunu sormak da ret sayılır.

## 6. Ekstre borcunu bildirmek

K18. İki soru da geçince (`tum_sorular_tamam: true`) `EkstreBorcSorgula` servisini çağırın.

K19. Şöyle söyleyin: "Freya Bank tahsilat biriminden arıyorum." Ardından her kart için: kartın son dört hanesi
("7319 ile biten kredi kartınız"), ekstre borcu, son ödeme tarihi ve kaç gündür gecikmede olduğu. Tutarlar Türk
lirasıdır ve Türkçe yazılır/okunur: `8.450,75 TL`.

K20. Birden fazla gecikmiş kart varsa en çok gecikmiş karttan başlayın ve kartları tek tek ele alın: bir kartın sözü
(veya sonucu) bitmeden diğerine geçmeyin. Her kart için en fazla bir söz alınır.

## 7. Tarihler

İş günleri Pazartesi–Cuma'dır; resmi tatiller hariç. Arife günleri (yarım gün) **iş günüdür**: söz tarihi olabilir ve
iş günü sayımına girer; yalnızca geri arama saati kısıtlıdır (K7). Freya Bank tatil takvimi:

| Tarih | Açıklama | Durum |
|---|---|---|
{holiday_rows()}

K21. **Son tarih**, kartın `gecikme_gun_sayisi` değerine göre belirlenir. Bugün sayılmaz; saymaya yarından başlanır.

| `gecikme_gun_sayisi` | Bant | Son tarih | İkna denemesi |
|---|---|---|---|
| 1–15 | erken | bugünden sonraki 7. iş günü | 1 |
| 16–60 | geç | bugünden sonraki 3. iş günü | 2 |

K22. Söz tarihi bugün veya sonrası, bir iş günü ve son tarihten sonra olmamalıdır.

K23. Müşteri son tarihten önceki bir hafta sonu veya tatil günü söylerse bir sonraki iş gününü önerin.

K24. Müşteri belirsiz bir dönem söylerse ("haftaya", "ay sonu", "maaş yatınca") kesin günü bir kez sorun. Yine
söylemezse son tarihi önerin.

K25. "Gelecek <gün>" veya "haftaya <gün>" bir sonraki takvim haftasındaki o gündür; "bu <gün>" içinde bulunulan
haftadakidir. Hafta Pazartesi başlar.

K26. Müşteri son tarihten sonraki bir tarih isterse kaydedebileceğiniz en geç tarihin son tarih olduğunu söyleyin ve
onu önerin. Müşteri son tarihi reddederse bu düz rettir (K32).

## 8. Tutarlar

K27. Önce ekstre borcunun **tamamını** isteyin. Asla "Ne kadar ödeyebilirsiniz?" diye sormayın. Her tutarı asistan
önerir.

K28. Müşteri tamamının çok fazla olduğunu söylerse **asgari ödeme tutarını** (`asgari_odeme_tutari`) bir kez önerin ve
şu cümleyi söyleyin: "{C.REST_OVERDUE}" Müşteri asgariyi reddederse bu düz rettir (K32).

K29. Müşteri asgari ile tamamı arasında (ikisi dahil) bir tutar söylerse kabul edin. Asgarinin altındaysa
kaydedilemeyeceğini söyleyin ve asgariyi bir kez önerin; kabul etmezse düz rettir (K32).

K30. Sözün tipi: tutar ekstre borcunun tamamıysa `TAMAMI`, asgari ödeme tutarıysa `ASGARI`, aradaysa `KISMI`.

## 9. Sözü almak

K31. İlk soru tam olarak şudur: "{C.FIRST_ASK}"

K32. Müşterinin söylediği bir tarih veya tutar asla ret değildir; bölüm 7 ve 8'e göre işleyin. Tarih ve tutar
söylemeden bugün ödemeye "hayır" demek, cevapsızlık veya bir teklifi reddetmek **düz ret**tir ve bir ikna denemesi
kullanır:
- 1. deneme: tamamı (müşteri tamamının fazla olduğunu zaten söylediyse asgari), **bu haftanın son iş günü**; bugün o
  günse gelecek haftanın son iş günü. Bu tarih son tarihten sonraysa son tarih.
- 2. deneme (yalnızca geç bant): asgari ödeme tutarı, son tarihte.

K33. Denemeler bitince durun; reddedilen bir teklifi tekrarlamayın. `SOZ_ALINAMADI` / `REDDETTI` ile kapatın.

K34. Müşteri hastalık, iş kaybı/işsizlik veya ailede bir ölümden söz ederse kısa bir dilek söyleyin ("{C.GET_WELL}";
ölüm için "{C.SORRY_LOSS}") ve ikna denemesi yapmayın. Müşteriyi Finansal Destek Ekibine aktarmayı önerin. Kabul
ederse `CagriAktar` servisini `FINANSAL_DESTEK` kuyruğuyla çağırın ve `AKTARILDI` / `FINANSAL_DESTEK` ile kapatın.
Kabul etmezse `SOZ_ALINAMADI` / `ZOR_DURUM` ile kapatın. Müşteri yine de kendisi bir tarih veya tutar söylerse sözü
bölüm 7 ve 8'e göre kaydedin. Bu kural K32 ve K40'tan önce gelir.

K35. Asla {", ".join(C.NEVER_OFFER)} veya bu belgede olmayan bir koşul önermeyin.

## 10. Teyit ve kayıt

K36. Kartın son dört hanesini, tutarı ve tarihi okuyun ve "{C.CONFIRM_Q}" diye sorun. `OdemeSozuKaydet` servisini
yalnızca net bir "evet"ten sonra çağırın.

K37. Müşteri bu adımda tarihi veya tutarı değiştirirse yeni değeri bölüm 7 ve 8'e göre kontrol edin ve tekrar okuyun.

K38. Kaydedilmiş bir söz aynı görüşmede değiştirilemez veya iptal edilemez. Müşteri isterse mobil uygulamadan
değiştirebileceğini söyleyin.

K39. Sözün kaydedildiğini yalnızca `OdemeSozuKaydet` `basarili: true` döndürdükten sonra söyleyin. Başarısız olursa
(`E500`) bir kez daha deneyin. Yine başarısız olursa kaydedemediğinizi söyleyin ve `SOZ_ALINAMADI` / `SISTEM_HATASI`
ile kapatın. Kayıttan sonra şu cümleyi söyleyin: "{C.SMS}"

## 11. Müşterilerin söylediği diğer şeyler

K40. Yeni bir ödeme planı, taksitlendirme, yapılandırma veya erteleme isteği: plan anlatmayın. `CagriAktar` servisini
`YAPILANDIRMA` kuyruğuyla çağırın ve `AKTARILDI` / `YAPILANDIRMA` ile kapatın.

K41. "Zaten ödedim": "{C.PAID_DELAY}" deyin, o kart için söz almayın, `NotEkle` servisini `ODENDI_BEYANI` tipiyle ve
`kart_id` ile çağırın. Başka gecikmiş kart yoksa `ODEME_YAPILMIS` ile kapatın.

K42. "Bu harcamayı ben yapmadım", "bu borç benim değil" veya "itiraz ettim": tartışmayın, o kart için söz almayın,
`NotEkle` servisini `ITIRAZ` tipiyle ve `kart_id` ile çağırın. Başka kart yoksa `SOZ_ALINAMADI` / `ITIRAZ` ile kapatın.

K43. Bir müşteri temsilcisiyle görüşme isteği: önce yardımcı olup olamayacağınızı bir kez sorun. Israr ederse
`CagriAktar` servisini `MUSTERI_TEMSILCISI` kuyruğuyla çağırın ve `AKTARILDI` / `TEMSILCI` ile kapatın. Bu kural
doğrulamadan önce de geçerlidir.

K44. Servislerden cevaplayamayacağınız bir soru (faiz oranı, kart limiti, harcama dökümü vb.): bu bilgiye sahip
olmadığınızı söyleyin. Rakam, tarih veya gerekçe uydurmayın.

K45. Müşteri iki kez konuşmak istemediğini söylerse `SOZ_ALINAMADI` / `REDDETTI` ile kapatın; kimlik doğrulanmadan
önce `DOGRULANAMADI` / `CEVAP_VERMEDI` ile kapatın.

## 12. Kapanış

K46. Her görüşme tam olarak bir `GorusmeKapat` çağrısıyla biter; son servis çağrısıdır. `sonuc_kodu` ve (tabloda
varsa) `gerekce_kodu` servis sözleşmesinin 10. bölümündedir.

K47. Birden fazla kart konuşulduysa sonuç: bir aktarım yapıldıysa `AKTARILDI`; en az bir söz kaydedildiyse
`SOZ_ALINDI`; bütün kartlar için "zaten ödedim" denildiyse `ODEME_YAPILMIS`; aksi halde sözsüz ilk kartın sonucu
(ödendi beyanı olan kartlar hariç).

K48. `NotEkle` yalnızca K41 ve K42 için kullanılır.

K49. Kapatmadan önce müşteriye teşekkür edip vedalaşın, ör. "{C.GOODBYE}"
"""


# ====================================================================== README.md (case folder)
FILES = [
    ("BRIEF.md", "Asistanın kuralları. Önce bunu okuyun."),
    ("README.md", "Bu dosya: klasördeki belgelerin listesi."),
    ("analiz.docx", "Ekstre borcu hattının süreç analizi (iş birimi). Arka plan ve gerekçeler; bağlayıcı kural değildir."),
    ("akis.drawio", "Görüşme akış şeması (draw.io / diagrams.net dosyası)."),
    ("duyurular.pdf", "Operasyon duyuruları. Yürürlük tarihi gelen duyuru BRIEF'teki kuralı değiştirir."),
    ("servis-sozlesmesi.docx", "Asistanın çağırdığı banka servisleri: alanlar, değerler, hata kodları, kapanış tablosu."),
    ("test-musterileri.xlsx", "Test ortamındaki müşteriler ve kartları (mock servis bu verilerle çalışır)."),
    ("soru-cevap.md", "Ekiplerden gelen sorular ve cevapları."),
] + [(f"ornek-konusma-{i}.md", "Örnek konuşma: kuralların nasıl uygulandığını gösterir, yeni kural koymaz.")
     for i in range(1, 7)]


def readme_md(contract_name="servis-sozlesmesi.docx"):
    rows = "\n".join(f"| `{n if n != 'servis-sozlesmesi.docx' else contract_name}` | {w} |" for n, w in FILES)
    return f"""# Freya Bank — Ekstre Borcu Hattı: belge klasörü

Bu klasör, Freya Bank kredi kartı ekstre borcu hattında çalışacak dijital asistan için hazırlanan belgeleri içerir.
Tüm veriler kurgusaldır.

| Dosya | Ne olduğu |
|---|---|
{rows}

## Öncelik

1. `duyurular.pdf` içindeki bir duyuru, yürürlük tarihinden itibaren yapılan aramalarda BRIEF'teki ilgili kuralı
   değiştirir. Hangi kuralın geçerli olduğuna **aramanın tarihi** (`now`) karar verir. Onaylanmayan veya süresi geçen
   duyurular uygulanmaz.
2. `BRIEF.md` diğer bütün belgelerden önce gelir.
3. Servis adları, alanlar ve kodlar için `{contract_name}` esastır.
4. `analiz.docx`, `akis.drawio`, `soru-cevap.md` ve örnek konuşmalar açıklayıcıdır; BRIEF ile çelişirlerse BRIEF geçerlidir.

## Test ortamı

Servisler test ortamında, `test-musterileri.xlsx` içindeki müşterilerle çalışan bir mock üzerinden çağrılır. Mock
iş kurallarını denetlemez (ör. tatil gününe söz kaydını reddetmez); kuralları uygulamak asistanın işidir.
"""


# ====================================================================== soru-cevap.md
QA = [
    ("Arife günü (ör. 28 Ekim 2026) ödeme sözü tarihi olabilir mi?",
     "Evet. Arife iş günüdür ve iş günü sayımına girer. Yalnızca geri arama 09:00–12:30 ile sınırlıdır."),
    ("Son tarih sayılırken bugün dahil mi?",
     "Hayır. Saymaya yarından başlanır. Örneğin Çarşamba 21 Ekim 2026'da geç bantta son tarih 3. iş günü olan "
     "26 Ekim Pazartesi'dir (2 Kasım 2026 öncesi aramalar için)."),
    ("Ekstre borcu müşterinin yaptığı kısmi ödemeleri içeriyor mu?",
     "`EkstreBorcSorgula` servisinin döndürdüğü `ekstre_borcu` güncel ödenmemiş tutardır. Asistan kendisi hesap yapmaz."),
    ("Müşteri tutarı yuvarlak söylerse (ör. 'beş bin üç yüz elli') kuruşlar ne olacak?",
     "Tutar ekstre borcuna eşitse tamamı kabul edilir. Asgari ile tamamı arasında herhangi bir tutar da kabul edilir; "
     "servise iki ondalıkla gönderilir."),
    ("Müşteri 'maaşım ayın 15'inde yatıyor' derse?",
     "Bu kesin bir gündür (ayın 15'i). Bölüm 7'ye göre kontrol edin: iş günü değilse sonraki iş günü, son tarihten "
     "sonraysa son tarih önerilir."),
    ("Müşteri 'haftaya' derse?",
     "Belirsiz dönemdir. Kesin günü bir kez sorun; yine gün söylemezse son tarihi önerin."),
    ("Müşteri kimlik sorularından önce borcun ne olduğunu sorarsa?",
     "Konuyu söylemeyin; soruların hesabını korumak için olduğunu bir kez açıklayın. Tekrar sorarsa veya cevap "
     "vermezse DOGRULANAMADI / CEVAP_VERMEDI ile kapatın."),
    ("İki kartı olan müşteri bir kart için 'ödedim' derse görüşme biter mi?",
     "Hayır. O kart için NotEkle ODENDI_BEYANI çağrılır ve diğer karta geçilir. Sonuç kodu BRIEF K47'ye göre seçilir."),
    ("Müşteri faiz oranını sorarsa?",
     "Asistanın bu bilgisi yoktur; bilgisi olmadığını söyler ve devam eder. Oran veya rakam uydurmaz."),
    ("Müşteri sözü kaydettikten sonra tarihi değiştirmek isterse?",
     "Kaydedilmiş söz aynı görüşmede değiştirilemez; mobil uygulamadan değiştirebileceği söylenir."),
    ("Asgari ödeme pilot uygulaması (asgarinin yarısı) hâlâ geçerli mi?",
     "Hayır. DUY-2026-028 30 Eylül 2026'da sona erdi; asgarinin altındaki tutarlar kaydedilmez."),
    ("Cumartesi günü söz alınabilir mi?",
     "Hayır. Cumartesi pilotu (DUY-2026-035) onaylanmadı; söz tarihi her zaman iş günü olmalıdır."),
    ("OdemeSozuKaydet E006 döndürürse tekrar denenir mi?",
     "Hayır. E006 o kart için bu görüşmede zaten söz kaydedildiği anlamına gelir; ikinci kayıt yapılmaz."),
]


def qa_md():
    body = "\n\n".join(f"**S{i}. {q}**\n\nC: {a}" for i, (q, a) in enumerate(QA, 1))
    return "# Soru – Cevap\n\nEkiplerin hazırlık sırasında sorduğu sorular ve operasyon ekibinin cevapları.\n\n" + body + "\n"


# ====================================================================== example conversations
def _fmt_json(x):
    return json.dumps(x, ensure_ascii=False)


def conversation_md(conv):
    c = C.BY_ID[conv["musteri_no"]]
    lines = [f"# Örnek Konuşma {conv['ornek']} — {conv['title']}", "",
             f"- Arama zamanı (`now`): `{conv['now']}` ({C.tr_date(C.d(conv['now']))}, saat {conv['now'][11:]})",
             f"- Müşteri: `{c['musteri_no']}` — {c['ad']} {c['soyad']} ({c['hitap']})",
             f"- Çağrı değişkenleri: `{_fmt_json(conv['variables'])}`", "",
             "Servis çağrıları `[Servis]` satırlarında, gönderilen gövde ve gelen cevapla gösterilmiştir.", ""]
    for t in conv["turns"]:
        if t[0] == "A":
            lines.append(f"**Asistan:** {t[1]}")
        elif t[0] == "M":
            who = "Müşteri" if not conv["family"].startswith("Üçüncü") else "Telefondaki kişi"
            lines.append(f"**{who}:** {t[1]}")
        else:
            status = "" if t[4] == 200 else f" (HTTP {t[4]})"
            lines.append(f"> [Servis] `{t[1]}` ← `{_fmt_json(t[2])}` → `{_fmt_json(t[3])}`{status}")
        lines.append("")
    return "\n".join(lines)


# ====================================================================== service contract
SERVICES = [
    dict(op="KimlikDogrula", path="/kimlik/dogrula", desc="Bir güvenlik cevabını kontrol eder. Toplam üç yanlış "
         "cevap kontrolü bitirir.",
         req=[("musteri_no", "string", "Evet", "Çağrı değişkeni musteri_no."),
              ("soru", "string (enum)", "Evet", "DOGUM_TARIHI veya TCKN_SON4."),
              ("cevap", "string", "Evet", "DOGUM_TARIHI için GG.AA.YYYY (ör. 14.02.1986). TCKN_SON4 için dört rakam "
               "(baştaki sıfırlar korunur, ör. 0285). Okunamayan değer E004 ile reddedilir ve yanlış sayılmaz.")],
         resp=[("basarili", "boolean", "İşlem yapıldıysa true."),
               ("hata_kodu", "string", "basarili false ise hata kodu (bölüm 11)."),
               ("dogrulandi", "boolean", "Bu cevap doğru mu."),
               ("kalan_hak", "integer", "Kalan yanlış cevap hakkı (başlangıçta 3)."),
               ("tum_sorular_tamam", "boolean", "İki soru da doğrulandıysa true."),
               ("ipucu", "string (enum)", "GUN_AY_YER_DEGISTI: doğum tarihinde gün ile ay yer değiştirmiş. Yanlış sayılmaz.")]),
    dict(op="EkstreBorcSorgula", path="/ekstre/borc-sorgula", desc="Müşterinin gecikmiş kredi kartı ekstre "
         "borçları. İki güvenlik sorusu geçilmeden E002 döner.",
         req=[("musteri_no", "string", "Evet", "Çağrı değişkeni musteri_no.")],
         resp=[("basarili", "boolean", "İşlem yapıldıysa true."), ("hata_kodu", "string", "Bölüm 11."),
               ("kartlar", "dizi", "Gecikmiş kartlar. Her eleman aşağıdaki alanları taşır."),
               ("kartlar[].kart_id", "string", "Kartın servis kimliği (OdemeSozuKaydet ve NotEkle için)."),
               ("kartlar[].urun", "string (enum)", "KREDI_KARTI."),
               ("kartlar[].kart_son4", "string", "Kart numarasının son dört hanesi (müşteriye söylenir)."),
               ("kartlar[].ekstre_borcu", "number", "Ödenmemiş ekstre borcu, TL, iki ondalık."),
               ("kartlar[].asgari_odeme_tutari", "number", "Asgari ödeme tutarı, TL."),
               ("kartlar[].son_odeme_tarihi", "string (date)", "Ekstrenin son ödeme tarihi, YYYY-AA-GG."),
               ("kartlar[].gecikme_gun_sayisi", "integer", "Son ödeme tarihinden bu yana geçen gün sayısı.")]),
    dict(op="OdemeSozuKaydet", path="/odeme-sozu/kaydet", desc="Bir kart için ödeme sözünü kaydeder. Kart başına "
         "görüşmede bir söz; ikincisi E006 ile reddedilir. Servis tatil veya son tarih kontrolü yapmaz.",
         req=[("musteri_no", "string", "Evet", "Çağrı değişkeni musteri_no."),
              ("kart_id", "string", "Evet", "EkstreBorcSorgula'dan gelen kart_id."),
              ("tutar", "number", "Evet", "TL, en fazla iki ondalık, sıfırdan büyük."),
              ("odeme_tarihi", "string (date)", "Evet", "YYYY-AA-GG."),
              ("soz_tipi", "string (enum)", "Evet", "TAMAMI, ASGARI veya KISMI (BRIEF K30).")],
         resp=[("basarili", "boolean", "Söz kaydedildiyse true."), ("hata_kodu", "string", "Bölüm 11."),
               ("soz_no", "string", "Kaydedilen sözün numarası.")]),
    dict(op="GeriAramaPlanla", path="/geri-arama/planla", desc="Müşteriye ulaşılamadığında geri arama randevusu.",
         req=[("musteri_no", "string", "Evet", "Çağrı değişkeni musteri_no."),
              ("tarih", "string (date)", "Evet", "YYYY-AA-GG."), ("saat", "string", "Evet", "SS:DD, 24 saat (ör. 18:30).")],
         resp=[("basarili", "boolean", "Randevu oluşturulduysa true."), ("hata_kodu", "string", "Bölüm 11."),
               ("randevu_no", "string", "Randevu numarası.")]),
    dict(op="CagriAktar", path="/cagri/aktar", desc="Görüşmeyi bir ekibe aktarır.",
         req=[("musteri_no", "string", "Evet", "Çağrı değişkeni musteri_no."),
              ("kuyruk", "string (enum)", "Evet", "FINANSAL_DESTEK, YAPILANDIRMA veya MUSTERI_TEMSILCISI.")],
         resp=[("basarili", "boolean", "Aktarım yapıldıysa true."), ("hata_kodu", "string", "Bölüm 11.")]),
    dict(op="NotEkle", path="/not/ekle", desc="Müşteri kaydına not ekler.",
         req=[("musteri_no", "string", "Evet", "Çağrı değişkeni musteri_no."),
              ("kart_id", "string", "Hayır", "Notun ilgili olduğu kart."),
              ("not_tipi", "string (enum)", "Evet", "ODENDI_BEYANI veya ITIRAZ."),
              ("aciklama", "string", "Evet", "Kısa açıklama, en fazla 500 karakter.")],
         resp=[("basarili", "boolean", "Not eklendiyse true."), ("hata_kodu", "string", "Bölüm 11."),
               ("not_no", "string", "Not numarası.")]),
    dict(op="GorusmeKapat", path="/gorusme/kapat", desc="Görüşmeyi sonuç koduyla kapatır. Her görüşmede bir kez ve "
         "en son çağrılır.",
         req=[("musteri_no", "string", "Evet", "Çağrı değişkeni musteri_no."),
              ("sonuc_kodu", "string (enum)", "Evet", "Bölüm 10."),
              ("gerekce_kodu", "string (enum)", "Hayır", "Bölüm 10; tabloda gerekçe yoksa gönderilmez.")],
         resp=[("basarili", "boolean", "Görüşme kapatıldıysa true."), ("hata_kodu", "string", "Bölüm 11.")]),
]
ERRORS = [
    ("E001", "Müşteri bulunamadı.", "Hayır"),
    ("E002", "Kimlik doğrulaması tamamlanmadı (EkstreBorcSorgula / OdemeSozuKaydet erken çağrıldı).", "Hayır"),
    ("E003", "Doğrulama hakkı bitti (üç yanlış cevap).", "Hayır"),
    ("E004", "Geçersiz biçim (ör. okunamayan tarih). Yanlış cevap sayılmaz.", "Doğru biçimle"),
    ("E005", "Kart bulunamadı veya müşteriye ait değil.", "Hayır"),
    ("E006", "Bu kart için bu görüşmede zaten söz kaydedildi.", "Hayır"),
    ("E007", "Geçersiz değer (izin verilen değerlerin dışında, tutar ≤ 0, geçmiş tarih).", "Doğru değerle"),
    ("E500", "Sistem hatası. Hiçbir şey kaydedilmedi. HTTP 500 ile döner.", "Evet (BRIEF K39: bir kez)"),
]


def contract_blocks():
    b = [("title", "Freya Bank — Ekstre Borcu Hattı Servis Sözleşmesi"),
         ("p", "Sürüm 2.3 — Test ortamı. Belge sahibi: Kartlı Ödemeler Entegrasyon Ekibi."),
         ("h1", "1. Genel"),
         ("li", "Bütün servisler HTTPS üzerinden POST ile çağrılır; gövde ve cevap UTF-8 JSON'dur."),
         ("li", "Adresler ortamın taban adresine göredir (ör. <taban>/kimlik/dogrula). Test ortamının taban adresi "
                "ayrıca bildirilir."),
         ("li", "Her cevapta basarili alanı vardır. İş hatalarında HTTP 200 ile basarili: false ve hata_kodu döner. "
                "Sistem hatasında HTTP 500 ve hata_kodu: E500 döner."),
         ("li", "Servisler BRIEF'teki iş kurallarını (tatil, son tarih, tutar aralığı) denetlemez."),
         ("li", "Kimlik doğrulama, müşteri ve görüşme bazında tutulur. Bir görüşmede yapılan bütün çağrılar "
                "kayıt defterine (ledger) yazılır ve değerlendirmede bu kayıt kullanılır."),
         ("h1", "2. Servis listesi"),
         ("table", [["No", "Servis", "Adres", "Ne yapar"]] + [[str(i + 1), s["op"], "POST " + s["path"], s["desc"]]
                                                              for i, s in enumerate(SERVICES)])]
    for i, s in enumerate(SERVICES):
        b += [("h1", f"{i + 3}. {s['op']}"), ("p", f"**Adres:** POST {s['path']}"), ("p", s["desc"]),
              ("h2", "İstek alanları"),
              ("table", [["Alan", "Tip", "Zorunlu", "Açıklama"]] + [list(r) for r in s["req"]]),
              ("h2", "Cevap alanları"),
              ("table", [["Alan", "Tip", "Açıklama"]] + [list(r) for r in s["resp"]])]
    final = b
    closing = [["sonuc_kodu", "gerekce_kodu", "Ne zaman"]] + [[o, r or "— (gönderilmez)", w] for o, r, w in C.CLOSE_TABLE]
    final += [("h1", "10. Kapanış tablosu (sonuç ve gerekçe kodları)"),
              ("p", "GorusmeKapat yalnızca bu tablodaki çiftlerle çağrılır. Gerekçesi olmayan sonuçlarda "
                    "gerekce_kodu gönderilmez."),
              ("sdt", [("table", closing)]),
              ("p", "Kuyruk ile gerekçe kodu aynı değildir: MUSTERI_TEMSILCISI kuyruğuna aktarılan görüşme TEMSILCI "
                    "gerekçesiyle kapatılır."),
              ("p", "Kullanımdan kalkan kodlar (gönderilmez): SESLI_MESAJ, HUKUKI_TAKIP."),
              ("h1", "11. Hata kodları"),
              ("table", [["Kod", "Anlamı", "Tekrar denenir mi"]] + [list(e) for e in ERRORS]),
              ("h1", "12. Örnek istek ve cevap"),
              ("p", 'POST /kimlik/dogrula  {"musteri_no": "FB-000001", "soru": "DOGUM_TARIHI", "cevap": "01.01.1980"}'),
              ("p", '200  {"basarili": true, "dogrulandi": false, "kalan_hak": 2, "tum_sorular_tamam": false}'),
              ("p", 'POST /odeme-sozu/kaydet  {"musteri_no": "FB-000001", "kart_id": "KRT-000001-01", "tutar": 1000.0, '
                    '"odeme_tarihi": "2026-01-02", "soz_tipi": "KISMI"}'),
              ("p", '500  {"basarili": false, "hata_kodu": "E500"}')]
    return final


def contract_md():
    out = []
    for x in contract_blocks():
        k = x[0]
        if k == "title":
            out.append(f"# {x[1]}\n")
        elif k == "h1":
            out.append(f"## {x[1]}\n")
        elif k == "h2":
            out.append(f"### {x[1]}\n")
        elif k == "li":
            out.append(f"- {x[1]}")
        elif k == "p":
            out.append(x[1] + "\n")
        elif k in ("table", "sdt"):
            rows = x[1] if k == "table" else x[1][0][1]
            out.append("| " + " | ".join(rows[0]) + " |")
            out.append("|" + "---|" * len(rows[0]))
            out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
            out.append("")
    return "\n".join(out) + "\n"


# ====================================================================== analysis
def analysis_blocks():
    return [
        ("title", "Ekstre Borcu Hattı — Süreç Analizi"),
        ("p", "Hazırlayan: Bireysel Tahsilat İş Analizi Ekibi. Tarih: Eylül 2026. Durum: onaylandı."),
        ("h1", "1. Amaç"),
        ("p", "Son ödeme tarihini geçirmiş kredi kartı ekstreleri için ilk aramaları dijital asistana devretmek. "
              "Hedef, erken dönemde ödeme sözü oranını artırmak ve zor durumdaki müşterileri doğru ekibe "
              "yönlendirmektir."),
        ("h1", "2. Mevcut durum"),
        ("table", [["Gösterge", "Ağustos 2026"], ["Günlük arama", "≈ 4.200"], ["Müşteriye ulaşma oranı", "%61"],
                   ["Söz oranı (ulaşılanlarda)", "%38"], ["Sözün tutma oranı", "%72"],
                   ["Ortalama görüşme süresi", "3 dk 40 sn"]]),
        ("h1", "3. Müşteri grupları"),
        ("li", "Unutanlar (1–15 gün): çoğu tam ödemeyi aynı hafta yapıyor. Kısa ve net bir hatırlatma yeterli."),
        ("li", "Zorlananlar (16–60 gün): asgari ödeme teklifi ve net bir son tarih işe yarıyor."),
        ("li", "Zor durumdakiler: iş kaybı, hastalık, ailede ölüm. Tahsilat dili yerine Finansal Destek Ekibine "
               "yönlendirme."),
        ("li", "İtiraz edenler: harcamayı tanımayanlar. Tartışılmadan not alınır; itiraz süreci ayrı işler."),
        ("h1", "4. Gözlenen sorunlar"),
        ("li", "Kimlik doğrulanmadan borcun yakınlara söylenmesi (KVKK riski)."),
        ("li", "Tatil günlerine söz alınması; söz tutma oranını düşürüyor."),
        ("li", "Servis hatasında müşteriye 'kaydedildi' denmesi; sonradan şikâyet."),
        ("li", "Doğum tarihinde gün ve ayın karıştırılması (ör. 04.09 / 09.04)."),
        ("h1", "5. Gereksinimler"),
        ("table", [["No", "Gereksinim", "BRIEF karşılığı"],
                   ["G1", "Doğrulamadan önce borçla ilgili hiçbir bilgi verilmez.", "K2, K6"],
                   ["G2", "İki soru: doğum tarihi, T.C. kimlik no son 4 hane; toplam 3 hak.", "K12–K16"],
                   ["G3", "Söz tarihi iş günü ve banda göre son tarihe kadar.", "K21–K26"],
                   ["G4", "Önce tamamı, sonra asgari; asgarinin altı kaydedilmez.", "K27–K30"],
                   ["G5", "Söz yalnızca açık onaydan sonra ve servis başarılıysa 'kaydedildi'.", "K36–K39"],
                   ["G6", "Zor durum → Finansal Destek; yapılandırma isteği → Yapılandırma Ekibi.", "K34, K40"],
                   ["G7", "Ödendi beyanı ve itiraz not olarak kaydedilir.", "K41, K42, K48"]]),
        ("h1", "6. Değerlendirilen ama seçilmeyen öneriler"),
        ("p", "Taslakta geç bant için 5 iş günü önerilmişti; risk ekibi 3 iş gününü onayladı (BRIEF K21). Erken bant "
              "için 'yaklaşık iki hafta' ifadesi de taslaktan kalmadır; geçerli kural BRIEF'teki tablodur."),
        ("p", "Asistanın müşteriye 'ne kadar ödeyebilirsiniz' diye sorması önerisi reddedildi."),
        ("h1", "7. Ölçüm"),
        ("p", "Her görüşme GorusmeKapat sonuç koduyla raporlanır. Söz kayıtları ve notlar servis kayıt defterinden "
              "okunur."),
    ]


# ====================================================================== announcements (PDF)
def announcements_md():
    return """# Freya Bank — Operasyon Duyuruları (Ekstre Borcu Hattı)

Duyurular yürürlük tarihinden itibaren yapılan **aramalara** uygulanır. Hangi kuralın geçerli olduğuna aramanın
tarihi karar verir; söz veya geri arama tarihi değil.

## DUY-2026-028 — Asgari ödeme pilotu (SÜRESİ DOLDU)

Yayın: 1 Eylül 2026 · Yürürlük: 1 Eylül 2026 · Bitiş: 30 Eylül 2026

Eylül ayı boyunca asgari ödeme tutarının yarısı da söz olarak kabul edildi. Pilot 30 Eylül 2026'da sona erdi.
1 Ekim 2026'dan itibaren asgari ödeme tutarının altındaki tutarlar kaydedilmez (BRIEF K29).

## DUY-2026-031 — Geri arama saatleri uzatıldı

Yayın: 12 Ekim 2026 · Yürürlük: **19 Ekim 2026**

19 Ekim 2026 ve sonrasında yapılan aramalarda geri arama saatleri hafta içi **09:00–20:00** (ikisi dahil) olarak
uygulanır. BRIEF K7'deki 09:00–18:00 aralığının yerine geçer. Arife günlerindeki 09:00–12:30 kısıtı değişmez.

## DUY-2026-034 — Geç bantta son tarih kısaldı

Yayın: 20 Ekim 2026 · Yürürlük: **2 Kasım 2026**

2 Kasım 2026 ve sonrasında yapılan aramalarda, gecikmesi 16–60 gün olan kartlar (geç bant) için son tarih
bugünden sonraki **2. iş günüdür** (önceki kural: 3. iş günü). İkna denemesi sayısı (2) ve erken bant değişmez.
2 Kasım'dan önce yapılan aramalarda 3. iş günü kuralı geçerlidir.

## DUY-2026-035 — Cumartesi söz kabulü önerisi (ONAYLANMADI)

Yayın: 21 Ekim 2026

Cumartesi günlerinin söz tarihi olarak kabul edilmesi önerisi risk komitesinde değerlendirildi ve **onaylanmadı**.
Kurallar değişmez: söz tarihi iş günü olmalıdır.

## DUY-2026-036 — 31 Aralık 2026

Yayın: 22 Ekim 2026

31 Aralık 2026 Perşembe **tatil değildir**; normal iş günüdür. Tatil takviminde değişiklik yoktur.
"""


def make_pdf(md_text: str, out: pathlib.Path) -> str:
    """pandoc -> standalone HTML -> headless Chrome print-to-pdf. Returns the tool chain used."""
    with tempfile.TemporaryDirectory() as td:
        md = pathlib.Path(td) / "a.md"
        html = pathlib.Path(td) / "a.html"
        md.write_text(md_text)
        css = ("<style>body{font-family:Helvetica,Arial,sans-serif;font-size:11pt;max-width:46em;margin:2em auto}"
               "h1{font-size:18pt}h2{font-size:13pt;margin-top:1.4em;border-bottom:1px solid #999}</style>")
        if shutil.which("pandoc"):
            subprocess.run(["pandoc", str(md), "-s", "--metadata", "title=Duyurular", "-o", str(html)], check=True,
                           capture_output=True)
            h = html.read_text().replace("</head>", css + "</head>")
            h = h.replace('<header id="title-block-header">\n<h1 class="title">Duyurular</h1>\n</header>', "")
            html.write_text(h)
        else:
            import html as H
            html.write_text("<html><head><meta charset='utf-8'>" + css + "</head><body><pre>" + H.escape(md_text)
                            + "</pre></body></html>")
        if not pathlib.Path(CHROME).exists():
            raise SystemExit("Chrome not found: cannot print duyurular.pdf")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={out}", html.as_uri()], check=True, capture_output=True, timeout=120)
    return "pandoc+chrome"


# ====================================================================== flow (draw.io)
def drawio(compressed: bool = False):
    nodes = [
        ("n1", "Açılış: dijital asistan + kayıt cümlesi\n'{ad} {soyad} ile mi görüşüyorum?'", 300, 20),
        ("n2", "Hattaki kişi müşteri mi?", 300, 110),
        ("n3", "Başkası: neden aradığını söyleme\nNe zaman ulaşılır? (bugün / sonraki iş günü\n09:00–18:00, arife 09:00–12:30)", 20, 200),
        ("n4", "GeriAramaPlanla", 20, 320),
        ("n5", "Kimlik: doğum tarihi (GG.AA.YYYY)\nsonra T.C. kimlik no son 4\nKimlikDogrula (toplam 3 hak)", 300, 200),
        ("n6", "3 yanlış / ret → DOGRULANAMADI", 560, 200),
        ("n7", "EkstreBorcSorgula\nEn çok gecikmiş karttan başla", 300, 320),
        ("n8", "Borcu bildir + 'Bu ödemeyi bugün yapabilir misiniz?'", 300, 410),
        ("n9", "Zor durum → Finansal Destek önerisi\nCagriAktar FINANSAL_DESTEK", 600, 320),
        ("n10", "Yapılandırma / taksit isteği\nCagriAktar YAPILANDIRMA", 600, 410),
        ("n11", "Zaten ödedim / İtiraz\nNotEkle (ODENDI_BEYANI / ITIRAZ)", 600, 500),
        ("n12", "Tarih ve tutar kuralları (bant, son tarih, asgari)\nİkna denemeleri: erken 1, geç 2", 300, 500),
        ("n13", "Özet + 'Onaylıyor musunuz?'\nOdemeSozuKaydet (hata: 1 tekrar)", 300, 590),
        ("n14", "SMS cümlesi; sonraki kart varsa ona geç", 300, 680),
        ("n15", "Teşekkür + vedalaşma\nGorusmeKapat (sonuç / gerekçe)", 300, 770),
    ]
    edges = [("n1", "n2", ""), ("n2", "n3", "başkası"), ("n3", "n4", "uygun saat"), ("n4", "n15", ""),
             ("n2", "n5", "evet / benim"), ("n5", "n6", "3 yanlış"), ("n6", "n15", ""), ("n5", "n7", "iki soru tamam"),
             ("n7", "n8", ""), ("n8", "n9", "zor durum"), ("n8", "n10", "yapılandırma"), ("n8", "n11", "ödedim / itiraz"),
             ("n8", "n12", "tarih / tutar / ret"), ("n12", "n13", "teklif kabul"), ("n13", "n14", "basarili"),
             ("n14", "n15", ""), ("n12", "n15", "denemeler bitti"), ("n9", "n15", ""), ("n10", "n15", ""),
             ("n11", "n15", "")]
    from xml.sax.saxutils import quoteattr
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    for nid, label, x, y in nodes:
        cells.append(f'<mxCell id="{nid}" value={quoteattr(label.replace(chr(10), "<br>"))} '
                     'style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{y}" width="240" height="64" as="geometry"/></mxCell>')
    for i, (s, t, label) in enumerate(edges):
        cells.append(f'<mxCell id="e{i}" value={quoteattr(label)} style="endArrow=classic;html=1;" edge="1" '
                     f'parent="1" source="{s}" target="{t}"><mxGeometry relative="1" as="geometry"/></mxCell>')
    model = ('<mxGraphModel dx="1200" dy="900" grid="1" gridSize="10"><root>' + "".join(cells)
             + "</root></mxGraphModel>")
    if compressed:   # what diagrams.net saves by default: base64(raw deflate(urlencode(model)))
        import base64
        import urllib.parse
        import zlib
        co = zlib.compressobj(9, zlib.DEFLATED, -15)
        raw = co.compress(urllib.parse.quote(model, safe="").encode()) + co.flush()
        model = base64.b64encode(raw).decode()
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<mxfile host="app.diagrams.net" version="24.7.0">'
            '<diagram id="akis" name="Ekstre Borcu Hattı Akışı">' + model + "</diagram></mxfile>\n")


# ====================================================================== test customers (xlsx)
def customers_xlsx(path):
    m = [["musteri_no", "ad", "soyad", "hitap", "dogum_tarihi", "tckn_son4", "test_notu"]]
    k = [["musteri_no", "kart_id", "urun", "kart_son4", "ekstre_borcu", "asgari_odeme_tutari", "son_odeme_tarihi",
          "gecikme_gun_sayisi"]]
    for c in C.CUSTOMERS:
        m.append([c["musteri_no"], c["ad"], c["soyad"], c["hitap"], O.Date(c["dogum_tarihi"]), O.Text(c["tckn_son4"]),
                  c["test_notu"]])
        for card in c["kartlar"]:
            k.append([c["musteri_no"], card["kart_id"], card["urun"], O.Text(card["kart_son4"]),
                      float(card["ekstre_borcu"]), float(card["asgari_odeme_tutari"]), O.Date(card["son_odeme_tarihi"]),
                      card["gecikme_gun_sayisi"]])
    notes = [["Açıklama"],
             ["Test ortamı müşterileri. Bütün veriler kurgusaldır."],
             ["Müşteriler sayfası güvenlik cevaplarını, Kartlar sayfası EkstreBorcSorgula cevabını içerir."],
             ["gecikme_gun_sayisi mock servis tarafından tablodaki gibi döndürülür (arama tarihine göre yeniden hesaplanmaz)."],
             ["tckn_son4 ve kart_son4 metindir; baştaki sıfırlar korunur."],
             ["Bir müşteride birden fazla kart olabilir (aynı musteri_no ile birden fazla satır)."],
             ["test_notu dolu olan müşteriler hata senaryoları içindir."]]
    O.xlsx(path, [("Müşteriler", m), ("Kartlar", k), ("Açıklamalar", notes)])


# ====================================================================== reference: openapi + mock data
def openapi():
    def schema_req(s):
        props, req = {}, []
        for name, typ, must, desc in s["req"]:
            p = {"type": "number" if typ == "number" else "string", "description": desc}
            if name == "soru":
                p["enum"] = ["DOGUM_TARIHI", "TCKN_SON4"]
            if name == "soz_tipi":
                p["enum"] = ["TAMAMI", "ASGARI", "KISMI"]
            if name == "kuyruk":
                p["enum"] = list(C.QUEUES)
            if name == "not_tipi":
                p["enum"] = list(C.NOTE_TYPES)
            if name == "sonuc_kodu":
                p["enum"] = list(C.OUTCOMES)
            if name == "gerekce_kodu":
                p["enum"] = list(C.REASONS)
            if typ.startswith("string (date)"):
                p["format"] = "date"
            props[name] = p
            if must == "Evet":
                req.append(name)
        return {"type": "object", "properties": props, "required": req}

    def schema_resp(s):
        props = {}
        for name, typ, desc in s["resp"]:
            if name.startswith("kartlar[]."):
                continue
            t = {"boolean": "boolean", "integer": "integer", "dizi": "array"}.get(typ, "string")
            p = {"type": t, "description": desc}
            if name == "ipucu":
                p["enum"] = ["GUN_AY_YER_DEGISTI"]
            if name == "kartlar":
                item = {}
                for n2, t2, d2 in s["resp"]:
                    if n2.startswith("kartlar[]."):
                        f = n2.split(".", 1)[1]
                        item[f] = {"type": {"number": "number", "integer": "integer"}.get(t2, "string"), "description": d2}
                        if f == "urun":
                            item[f]["enum"] = ["KREDI_KARTI"]
                p["items"] = {"type": "object", "properties": item}
            props[name] = p
        return {"type": "object", "properties": props}

    paths = {}
    for s in SERVICES:
        paths[s["path"]] = {"post": {"operationId": s["op"], "summary": s["desc"], "requestBody": {
            "required": True, "content": {"application/json": {"schema": schema_req(s)}}}, "responses": {
            "200": {"description": "basarili false ise işlem yapılmadı.",
                    "content": {"application/json": {"schema": schema_resp(s)}}},
            "500": {"description": "E500: sistem hatası, hiçbir şey kaydedilmedi; tekrar denenebilir."}}}}
    return {"openapi": "3.0.3", "info": {"title": "Freya Bank Ekstre Borcu Hattı servisleri (prova)", "version": "2.3",
            "description": "Reference reading of servis-sozlesmesi.docx (rehearsal). Not part of the case folder."},
            "servers": [{"url": "https://example-mock.invalid"}], "paths": paths}


def mock_customers():
    return [dict(customer_id=c["musteri_no"],
                 identity={"DOGUM_TARIHI": C.ddmmyyyy(c["dogum_tarihi"]), "TCKN_SON4": c["tckn_son4"]},
                 kartlar=c["kartlar"], faults={"OdemeSozuKaydet": "E500"} if c["test_notu"] else {})
            for c in C.CUSTOMERS]


# ====================================================================== cases.json / expected.json
def _system_view(conv):
    led = C.ledger(conv)
    close = next(x["body"] for x in led if x["op"] == "GorusmeKapat")
    return dict(
        outcome=C.OUTCOMES[close["sonuc_kodu"]],
        reason=C.REASONS.get(close.get("gerekce_kodu")) if close.get("gerekce_kodu") else None,
        promises=[dict(product_id=x["body"]["kart_id"], amount=x["body"]["tutar"], date=x["body"]["odeme_tarihi"])
                  for x in led if x["op"] == "OdemeSozuKaydet"],
        notes=[dict(product_id=x["body"].get("kart_id"), reason=C.NOTE_TYPES[x["body"]["not_tipi"]])
               for x in led if x["op"] == "NotEkle"],
        callbacks=[dict(date=x["body"]["tarih"], time=x["body"]["saat"]) for x in led if x["op"] == "GeriAramaPlanla"],
        transfers=[dict(queue=C.QUEUES[x["body"]["kuyruk"]]) for x in led if x["op"] == "CagriAktar"])


CHECKS = {
    "TRF-01": ["opening sentence verbatim; right-party question with {ad} {soyad}",
               "no banned word (with suffixes) before both questions pass",
               "DOB sent as 14.02.1986 (GG.AA.YYYY)", "first ask verbatim; promise read back with 'Onaylıyor musunuz?'",
               "soz_tipi TAMAMI", "SMS sentence after the promise", "GorusmeKapat last, SOZ_ALINDI without gerekce"],
    "TRF-02": ["'Buyurun.' is not a confirmation: right-party question asked a second time",
               "after 'too much' the minimum is offered once with 'Kalan tutar gecikmede kalmaya devam eder.'",
               "29 Ekim is a holiday: the next business day 30 Ekim is proposed (deadline 2 Kasım)", "soz_tipi ASGARI"],
    "TRF-03": ["nothing about the reason is said to the spouse; no banned word", "relative's offer to pay is declined",
               "28 Ekim is arife: 19:00 is outside 09:00-12:30, one re-ask, 11:00 booked",
               "ULASILAMADI / GERI_ARAMA"],
    "TRF-04": ["04.09.1979 sent first (numeric date read day-month-year)",
               "ipucu GUN_AY_YER_DEGISTI: month asked by name, not counted", "paid-delay sentence; NotEkle ODENDI_BEYANI with kart_id",
               "no promise; ODEME_YAPILMIS without gerekce"],
    "TRF-05": ["robot answer verbatim, then the right-party question again",
               "'Geçmiş olsun.'; no persuasion; transfer offered and accepted", "CagriAktar FINANSAL_DESTEK, then AKTARILDI / FINANSAL_DESTEK"],
    "TRF-06": ["scam answer before verification contains no banned word",
               "most overdue card (5502, 40 days) first", "DUY-2026-034 in force (now 2026-11-03): geç deadline = 2nd business day = 5 Kasım",
               "attempt 1 date = min(this week's last business day 6 Kasım, deadline 5 Kasım) = 5 Kasım",
               "second card disputed: NotEkle ITIRAZ with its kart_id, no promise for it", "SOZ_ALINDI (one promise recorded)"],
    "TRF-07": ["OdemeSozuKaydet tried exactly twice", "never says 'kaydedildi'; no SMS sentence",
               "SOZ_ALINAMADI / SISTEM_HATASI"],
    "TRF-08": ["three wrong DOB answers (none is the swapped date)", "nothing about the account is said",
               "app / branch advice; DOGRULANAMADI / HATALI_CEVAP"],
    "TRF-09": ["erken band (9 days): exactly one persuasion attempt (full, Fri 23 Ekim)", "the refused offer is not repeated",
               "SOZ_ALINAMADI / REDDETTI"],
    "TRF-10": ["no plan is described or offered", "CagriAktar YAPILANDIRMA; AKTARILDI / YAPILANDIRMA"],
    "TRF-11": ["'gelecek çarşamba' on Thu 22 Ekim = Wed 28 Ekim (arife = business day, before deadline 3 Kasım)",
               "2.000 TL below the minimum: not recordable, minimum offered once", "soz_tipi ASGARI"],
    "TRF-12": ["geç band before DUY-2026-034: deadline = 3rd business day = 26 Ekim",
               "30 Ekim is after the deadline: the deadline is offered", "soz_tipi TAMAMI"],
    "TRF-13": ["DUY-2026-031 in force (now 2026-10-21): 19:30 today is inside 09:00-20:00 and booked without a re-ask",
               "a build with the BRIEF's stale 18:00 window would re-ask: fail", "ULASILAMADI / GERI_ARAMA"],
}


def cases():
    out = []
    for conv in C.conversations():
        c = C.BY_ID[conv["musteri_no"]]
        out.append(dict(
            id=conv["id"], brief="tr-final", family=conv["family"], title=conv["title"],
            source=f"ornek-konusma-{conv['ornek']}.md" if conv["ornek"] else None,
            mock_customer=conv["musteri_no"], variables=conv["variables"],
            identity={"DOGUM_TARIHI": C.ddmmyyyy(c["dogum_tarihi"]), "TCKN_SON4": c["tckn_son4"]},
            products=[dict(product_id=k["kart_id"], type="credit_card", card_last4=k["kart_son4"], past_due=k["ekstre_borcu"],
                           days_late=k["gecikme_gun_sayisi"], minimum_payment=k["asgari_odeme_tutari"]) for k in c["kartlar"]],
            faults={"OdemeSozuKaydet": "E500"} if c["test_notu"] else {},
            customer_lines=[t[1] for t in conv["turns"] if t[0] == "M"],
            agent_lines_reference=[t[1] for t in conv["turns"] if t[0] == "A"],
            service_calls=[dict(op=t[1], body=t[2], response=t[3], http=t[4]) for t in conv["turns"] if t[0] == "S"],
            expected_ledger=C.ledger(conv),
            expected=_system_view(conv),
            checks=CHECKS[conv["id"]]))
    return out


def expected():
    ref_now = "2026-10-21T10:30"
    return {
        "_about": "Core values a correct extraction of FreyaBank-Rehearsal/ must yield. 'leaves' are JSON pointers "
                  "into the Spec (paths as tests/golden/spec-a.json) where the schema has a home for them; values are "
                  "the rules in force at reference_now. Everything else is grouped by topic. Contract names "
                  "(KimlikDogrula, sonuc_kodu, ...) must be used verbatim on the wire.",
        "reference_now": ref_now,
        "leaves": {
            "/bank/name": "Freya Bank",
            "/bank/language": "tr",
            "/call_variables/customer_key": "musteri_no",
            "/call_variables/now": "now",
            "/addressing/customer": "<v:ad> <v:hitap>",
            "/right_party/max_asks": 2,
            "/right_party/accept_own_name": True,
            "/right_party/on_unresolved": "S_UNCLEAR",
            "/identity/questions/0/field_value": "DOGUM_TARIHI",
            "/identity/questions/0/kind": "date",
            "/identity/questions/0/numeric_order": "DMY",
            "/identity/questions/0/wire_format": "%d.%m.%Y",
            "/identity/questions/1/field_value": "TCKN_SON4",
            "/identity/questions/1/kind": "digits",
            "/identity/questions/1/length": 4,
            "/identity/one_at_a_time": True,
            "/identity/max_wrong_total": 3,
            "/identity/hints/0/value": "GUN_AY_YER_DEGISTI",
            "/identity/hints/0/counts_as_wrong": False,
            "/identity/decline/explain_times": 1,
            "/identity/decline/max_declines": 2,
            "/identity/decline/purpose_question_counts": True,
            "/third_party/relative_may_verify": False,
            "/third_party/relative_may_pay": False,
            "/third_party/disclose": "nothing_beyond_opening",
            "/third_party/callback/date_rule/include_today": True,
            "/third_party/callback/date_rule/business_days_ahead": 1,
            "/third_party/callback/windows/0/from": "09:00",
            "/third_party/callback/windows/0/to": "20:00",
            "/third_party/callback/after_now": True,
            "/third_party/callback/reask_limit": 1,
            "/products/fields/list": "kartlar",
            "/products/fields/id": "kart_id",
            "/products/fields/past_due": "ekstre_borcu",
            "/products/fields/days_late": "gecikme_gun_sayisi",
            "/products/types/KREDI_KARTI/floor/field": "asgari_odeme_tutari",
            "/calendar/business_weekdays": [0, 1, 2, 3, 4],
            "/calendar/holidays": sorted(C.HOLIDAYS),
            "/calendar/count_from": "after_today",
            "/calendar/numeric_order": "DMY",
            "/calendar/this_next": {"this": "current_week", "next": "following_week"},
            "/bands": [
                {"key": "erken", "days_late_min": 1, "days_late_max": 15,
                 "deadline": {"kind": "nth_business_day_after_today", "n": 7}, "attempts": 1},
                {"key": "geç", "days_late_min": 16, "days_late_max": 60,
                 "deadline": {"kind": "nth_business_day_after_today", "n": 3}, "attempts": 2}],
            "/promise_date/earliest": {"kind": "today"},
            "/promise_date/latest": {"kind": "deadline"},
            "/promise_date/business_day_only": True,
            "/promise_date/non_business_within_deadline": "offer_next_business_day",
            "/promise_date/after_deadline": "offer_deadline",
            "/promise_date/vague": {"ask_exact_times": 1, "then": "propose_deadline"},
            "/amounts/first": {"kind": "full"},
            "/amounts/never_ask_customer": True,
            "/amounts/too_much/offer": {"kind": "floor"},
            "/amounts/too_much/times": 1,
            "/amounts/accept_min": {"kind": "floor"},
            "/amounts/accept_max": {"kind": "full"},
            "/amounts/below_floor/times": 1,
            "/amounts/below_floor/then": "flat_refusal",
            "/negotiation/first_ask/single": C.FIRST_ASK,
            "/negotiation/ladder/0/attempt": 1,
            "/negotiation/ladder/0/bands": ["all"],
            "/negotiation/ladder/0/amount": {"kind": "floor_if_too_much_else_full"},
            "/negotiation/ladder/0/date": {"kind": "last_business_day_of_week", "if_today": "next_week",
                                           "_capped_at": "deadline"},
            "/negotiation/ladder/1/attempt": 2,
            "/negotiation/ladder/1/bands": ["geç"],
            "/negotiation/ladder/1/amount": {"kind": "floor"},
            "/negotiation/ladder/1/date": {"kind": "deadline"},
            "/negotiation/no_repeat_refused_offer": True,
            "/confirmation/question": C.CONFIRM_Q,
            "/recording/tries": 2,
            "/recording/on_all_failed": "S_SERVICE_ERROR",
            "/notes/enabled": True,
            "/outcomes/reasonless_outcomes": ["SOZ_ALINDI", "ODEME_YAPILMIS"],
        },
        "tool_roles": {"verify": "KimlikDogrula", "account": "EkstreBorcSorgula", "promise": "OdemeSozuKaydet",
                       "callback": "GeriAramaPlanla", "transfer": "CagriAktar", "note": "NotEkle", "close": "GorusmeKapat"},
        "tool_fields": {
            "KimlikDogrula": {"customer_key": "musteri_no", "field": "soru", "answer": "cevap",
                              "result": "dogrulandi", "left": "kalan_hak", "all_done": "tum_sorular_tamam",
                              "hint": "ipucu", "ok": "basarili", "error": "hata_kodu"},
            "OdemeSozuKaydet": {"product": "kart_id", "amount": "tutar", "date": "odeme_tarihi",
                                "derived_enum": {"field": "soz_tipi", "rule": "TAMAMI if amount == ekstre_borcu, "
                                                 "ASGARI if amount == asgari_odeme_tutari, else KISMI"}},
            "GeriAramaPlanla": {"date": "tarih", "time": "saat"},
            "CagriAktar": {"queue": "kuyruk"},
            "NotEkle": {"product": "kart_id", "type": "not_tipi", "text": "aciklama"},
            "GorusmeKapat": {"outcome": "sonuc_kodu", "reason": "gerekce_kodu (omitted when the table has none)"}},
        "code_list": {"outcome": C.OUTCOMES, "reason": C.REASONS, "queue": C.QUEUES, "note": C.NOTE_TYPES,
                      "close_pairs": [[o, r] for o, r, _ in C.CLOSE_TABLE],
                      "retired_never_send": ["SESLI_MESAJ", "HUKUKI_TAKIP"],
                      "trap": "queue MUSTERI_TEMSILCISI closes with gerekce TEMSILCI (not the queue name)"},
        "situations": {
            "promise": ["SOZ_ALINDI", None], "paid": ["ODEME_YAPILMIS", None],
            "hardship_transfer": ["AKTARILDI", "FINANSAL_DESTEK", "queue FINANSAL_DESTEK"],
            "restructure_transfer": ["AKTARILDI", "YAPILANDIRMA", "queue YAPILANDIRMA"],
            "human_transfer": ["AKTARILDI", "TEMSILCI", "queue MUSTERI_TEMSILCISI"],
            "refused": ["SOZ_ALINAMADI", "REDDETTI"], "hardship_declined": ["SOZ_ALINAMADI", "ZOR_DURUM"],
            "dispute": ["SOZ_ALINAMADI", "ITIRAZ", "note ITIRAZ"], "service_error": ["SOZ_ALINAMADI", "SISTEM_HATASI"],
            "id_failed": ["DOGRULANAMADI", "HATALI_CEVAP"], "id_declined": ["DOGRULANAMADI", "CEVAP_VERMEDI"],
            "callback": ["ULASILAMADI", "GERI_ARAMA"], "no_callback": ["ULASILAMADI", "GERI_ARAMA_YOK"],
            "wrong_number": ["ULASILAMADI", "YANLIS_NUMARA"], "deceased": ["ULASILAMADI", "VEFAT"],
            "unclear": ["ULASILAMADI", "BELIRSIZ"]},
        "multi_product": {"order": "most days_late first", "one_at_a_time": True, "one_promise_per_product": True,
                          "close_precedence": ["transfer -> AKTARILDI", "any promise -> SOZ_ALINDI",
                                               "all paid -> ODEME_YAPILMIS", "else first unpromised non-paid product"]},
        "banned_before_verification_must_include": C.BANNED_BEFORE_VERIFICATION,
        "banned_morphology": "suffixed forms count: borcunuz, ödemeniz, kartınızın, ekstrenizin, gecikmeli ...",
        "never_offer_must_include": C.NEVER_OFFER,
        "never_ask_must_include": C.NEVER_ASK,
        "verbatim_sentences": {"opening": C.OPENING, "right_party_ask": "{ad} {soyad} ile mi görüşüyorum?",
                               "first_ask": C.FIRST_ASK, "confirm_question": C.CONFIRM_Q, "sms": C.SMS,
                               "rest_overdue": C.REST_OVERDUE, "scam": C.SCAM, "robot": C.ROBOT,
                               "sorry_loss": C.SORRY_LOSS, "paid_delay": C.PAID_DELAY},
        "language": {"amount_format": "8.450,75 TL (dot thousands, comma decimals)",
                     "date_spoken": "21 Ekim 2026 Çarşamba", "weekday_names": C.TR_DAYS, "month_names": C.TR_MONTHS,
                     "two_digit_year": "19xx", "numeric_date_order": "DMY"},
        "superseded_values": [
            {"path": "/third_party/callback/windows/0/to", "brief": "18:00", "announcement": "DUY-2026-031",
             "value": "20:00", "effective_from": "2026-10-19", "in_force_at_reference_now": "20:00",
             "test": "TRF-13"}],
        "dated_overrides": [
            {"announcement": "DUY-2026-034", "path": "/bands/1/deadline/n", "before": 3, "value": 2,
             "effective_from": "2026-11-02", "decided_by": "call date (now)",
             "expect": "n=3 when now < 2026-11-02 (TRF-02, TRF-12), n=2 when now >= 2026-11-02 (TRF-06). Baking "
                       "either value fails one of them; the builder must emit a now-conditioned deadline or at "
                       "least raise it in meta.residual_rules / warnings."}],
        "residual_rules": [
            {"what": "arife (half-day) callback window 09:00-12:30; arife counts as a business day for promises",
             "dates": sorted(C.HALF_DAYS), "test": "TRF-03 (callback), TRF-11 (promise on arife)"},
            {"what": "attempt-1 date is capped at the deadline", "test": "TRF-06"},
            {"what": "soz_tipi derived from the amount", "test": "TRF-01, TRF-02, TRF-06, TRF-11, TRF-12"}],
        "rejected_changes": [
            {"announcement": "DUY-2026-035", "what": "Saturday promises", "expect": "business_weekdays stays Mon-Fri"},
            {"announcement": "DUY-2026-036", "what": "2026-12-31 is NOT a holiday",
             "expect": "2026-12-31 absent from /calendar/holidays"},
            {"announcement": "DUY-2026-028", "what": "half-minimum pilot expired 2026-09-30",
             "expect": "floor stays asgari_odeme_tutari"}],
        "distractors": {"analiz.docx": "'5 iş günü' (draft, rejected) and 'yaklaşık iki hafta' must not become a deadline",
                        "servis-sozlesmesi.docx": "example bodies use FB-000001 / 2026-01-02; retired codes SESLI_MESAJ, HUKUKI_TAKIP"},
        "file_traps": {"test-musterileri.xlsx": "dates are real Excel date cells (serial numbers with a dd.mm.yyyy "
                                                "format), tckn_son4 '0285' is text, amounts are numbers with #,##0.00",
                       "servis-sozlesmesi.docx": "the closing table sits inside a content control (w:sdt)",
                       "akis.drawio": "uncompressed mxGraph XML (labels in value attributes with <br>); the -md variant folder holds the compressed form diagrams.net saves by default (base64 + raw deflate + URL-encoding)",
                       "duyurular.pdf": "text PDF printed by Chrome"},
    }


# ====================================================================== main
def write_case_folder(folder: pathlib.Path, contract_as_md: bool):
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    contract_name = "servis-sozlesmesi.md" if contract_as_md else "servis-sozlesmesi.docx"
    (folder / "BRIEF.md").write_text(brief_md())
    (folder / "README.md").write_text(readme_md(contract_name))
    (folder / "soru-cevap.md").write_text(qa_md())
    for conv in C.conversations():
        if conv["ornek"]:
            (folder / f"ornek-konusma-{conv['ornek']}.md").write_text(conversation_md(conv))
    O.docx(folder / "analiz.docx", analysis_blocks())
    if contract_as_md:
        (folder / "servis-sozlesmesi.md").write_text(contract_md())
    else:
        O.docx(folder / "servis-sozlesmesi.docx", contract_blocks())
    (folder / "akis.drawio").write_text(drawio(compressed=contract_as_md))
    customers_xlsx(folder / "test-musterileri.xlsx")


def main():
    # Chrome stamps the PDF, so it is reprinted only when the announcements text changed (keeps git clean).
    old_pdf = (CASE / "duyurular.pdf").read_bytes() if (CASE / "duyurular.pdf").exists() else None
    same_text = (REF / "duyurular.md").exists() and (REF / "duyurular.md").read_text() == announcements_md()
    write_case_folder(CASE, contract_as_md=False)
    if old_pdf and same_text:
        (CASE / "duyurular.pdf").write_bytes(old_pdf)
    else:
        make_pdf(announcements_md(), CASE / "duyurular.pdf")
    write_case_folder(CASE_MD, contract_as_md=True)
    shutil.copy(CASE / "duyurular.pdf", CASE_MD / "duyurular.pdf")
    REF.mkdir(exist_ok=True)
    (REF / "openapi.json").write_text(json.dumps(openapi(), ensure_ascii=False, indent=1) + "\n")
    (REF / "mock-customers.json").write_text(json.dumps(mock_customers(), ensure_ascii=False, indent=1) + "\n")
    (REF / "duyurular.md").write_text(announcements_md())
    (HERE / "cases.json").write_text(json.dumps(cases(), ensure_ascii=False, indent=1) + "\n")
    (HERE / "expected.json").write_text(json.dumps(expected(), ensure_ascii=False, indent=1) + "\n")
    zp = HERE / "FreyaBank-Rehearsal.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(CASE.iterdir()):
            zi = zipfile.ZipInfo(f"FreyaBank-Rehearsal/{p.name}", (2026, 10, 11, 9, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, p.read_bytes())
    print("wrote", CASE, CASE_MD, REF, HERE / "cases.json", HERE / "expected.json", zp)


if __name__ == "__main__":
    main()
