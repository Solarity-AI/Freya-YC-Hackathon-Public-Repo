"""Single source of truth for the Turkish rehearsal case (testbed/tr-final).

Synthetic Freya Bank credit-card statement-debt line in Turkish. Everything the case folder, cases.json, expected.json
and the reference mock data say is generated from this module by make_case.py, so the conversations, the ledgers and
the test customers can never disagree. Rehearsal values live in testbed/ only (never in builder/ runtime/ harness/).
Standard library only.
"""
from __future__ import annotations

import datetime as dt

# ---------------------------------------------------------------- calendar (the rules the BRIEF states)
HOLIDAYS = {  # full-day public holidays (not business days)
    "2026-10-29": "Cumhuriyet Bayramı",
    "2027-01-01": "Yılbaşı",
    "2027-03-09": "Ramazan Bayramı 1. gün",
    "2027-03-10": "Ramazan Bayramı 2. gün",
    "2027-03-11": "Ramazan Bayramı 3. gün",
    "2027-04-23": "Ulusal Egemenlik ve Çocuk Bayramı",
    "2027-05-01": "Emek ve Dayanışma Günü",
    "2027-05-16": "Kurban Bayramı 1. gün",
    "2027-05-17": "Kurban Bayramı 2. gün",
    "2027-05-18": "Kurban Bayramı 3. gün",
    "2027-05-19": "Kurban Bayramı 4. gün ve Atatürk'ü Anma, Gençlik ve Spor Bayramı",
}
HALF_DAYS = {  # arife: a business day, but callbacks only 09:00-12:30
    "2026-10-28": "Cumhuriyet Bayramı arifesi",
    "2027-03-08": "Ramazan Bayramı arifesi",
    "2027-05-15": "Kurban Bayramı arifesi",
}
NOT_HOLIDAYS = ["2026-12-31"]  # announcement DUY-2026-036

TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım",
             "Aralık"]
TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

# bands: (min, max, nth business day after today, persuasion attempts). Geç band n is dated (DUY-2026-034).
BANDS = [("erken", 1, 15, 7, 1), ("geç", 16, 60, 3, 2)]
LATE_N_FROM = ("2026-11-02", 2)          # DUY-2026-034: calls on/after this date -> 2nd business day
CALLBACK_WINDOW = [("09:00", "18:00")]    # BRIEF
CALLBACK_WINDOW_FROM = ("2026-10-19", [("09:00", "20:00")])   # DUY-2026-031
HALF_DAY_CALLBACK = ("09:00", "12:30")


def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def is_bd(day: dt.date) -> bool:
    return day.weekday() < 5 and day.isoformat() not in HOLIDAYS


def nth_bd_after(today: dt.date, n: int) -> dt.date:
    x, k = today, 0
    while k < n:
        x += dt.timedelta(days=1)
        if is_bd(x):
            k += 1
    return x


def next_bd_on_or_after(day: dt.date) -> dt.date:
    while not is_bd(day):
        day += dt.timedelta(days=1)
    return day


def band(days_late: int):
    for name, lo, hi, n, attempts in BANDS:
        if lo <= days_late <= hi:
            return name, n, attempts
    raise ValueError(days_late)


def deadline(now: str, days_late: int) -> dt.date:
    name, n, _ = band(days_late)
    if name == "geç" and now[:10] >= LATE_N_FROM[0]:
        n = LATE_N_FROM[1]
    return nth_bd_after(d(now), n)


def last_bd_of_week(today: dt.date) -> dt.date:
    """Attempt-1 date: this week's last business day; next week's if today is that day."""
    def lbd(monday):
        x = monday + dt.timedelta(days=6)
        while not is_bd(x):
            x -= dt.timedelta(days=1)
        return x
    monday = today - dt.timedelta(days=today.weekday())
    x = lbd(monday)
    if x <= today:
        x = lbd(monday + dt.timedelta(days=7))
    return x


def callback_windows(now: str, day: dt.date):
    if day.isoformat() in HALF_DAYS:
        return [HALF_DAY_CALLBACK]
    return CALLBACK_WINDOW_FROM[1] if now[:10] >= CALLBACK_WINDOW_FROM[0] else CALLBACK_WINDOW


def tl(x: float) -> str:
    """8450.75 -> '8.450,75 TL'"""
    s = f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return s + " TL"


def tr_date(day: dt.date, weekday: bool = True, year: bool = True) -> str:
    s = f"{day.day} {TR_MONTHS[day.month - 1]}"
    if year:
        s += f" {day.year}"
    if weekday:
        s += f" {TR_DAYS[day.weekday()]}"
    return s


def ddmmyyyy(iso: str) -> str:
    y, m, dd = iso.split("-")
    return f"{dd}.{m}.{y}"


# ---------------------------------------------------------------- test customers (test-musterileri.xlsx)
def _card(kart_id, son4, borc, asgari, son_odeme, gecikme):
    return dict(kart_id=kart_id, urun="KREDI_KARTI", kart_son4=son4, ekstre_borcu=borc, asgari_odeme_tutari=asgari,
                son_odeme_tarihi=son_odeme, gecikme_gun_sayisi=gecikme)


CUSTOMERS = [
    dict(musteri_no="FB-240117", ad="Ayşe", soyad="Yılmaz", hitap="Hanım", dogum_tarihi="1986-02-14", tckn_son4="3058",
         kartlar=[_card("KRT-240117-01", "7319", 8450.75, 3380.30, "2026-10-15", 6)], test_notu=""),
    dict(musteri_no="FB-240233", ad="Mehmet", soyad="Kaya", hitap="Bey", dogum_tarihi="1985-01-03", tckn_son4="6614",
         kartlar=[_card("KRT-240233-01", "2290", 5350.00, 2140.00, "2026-10-05", 22)], test_notu=""),
    dict(musteri_no="FB-240318", ad="Zeynep", soyad="Demir", hitap="Hanım", dogum_tarihi="1992-07-21", tckn_son4="4402",
         kartlar=[_card("KRT-240318-01", "6045", 12780.40, 5112.16, "2026-10-15", 12)], test_notu=""),
    dict(musteri_no="FB-240402", ad="Can", soyad="Öztürk", hitap="Bey", dogum_tarihi="1979-04-09", tckn_son4="9127",
         kartlar=[_card("KRT-240402-01", "3376", 2315.60, 926.24, "2026-10-15", 7)], test_notu=""),
    dict(musteri_no="FB-240561", ad="Elif", soyad="Şahin", hitap="Hanım", dogum_tarihi="1990-11-30", tckn_son4="0285",
         kartlar=[_card("KRT-240561-01", "8812", 19640.00, 7856.00, "2026-09-17", 34)], test_notu=""),
    dict(musteri_no="FB-240699", ad="Burak", soyad="Arslan", hitap="Bey", dogum_tarihi="1983-06-02", tckn_son4="7751",
         kartlar=[_card("KRT-240699-01", "5502", 14200.00, 5680.00, "2026-09-24", 40),
                  _card("KRT-240699-02", "1187", 3120.90, 1248.36, "2026-10-26", 8)], test_notu=""),
    dict(musteri_no="FB-240744", ad="Selin", soyad="Aydın", hitap="Hanım", dogum_tarihi="1995-08-04", tckn_son4="5530",
         kartlar=[_card("KRT-240744-01", "9064", 4100.00, 1640.00, "2026-10-15", 6)],
         test_notu="OdemeSozuKaydet bu müşteri için her denemede HTTP 500 / E500 döner (hata senaryosu)."),
    dict(musteri_no="FB-240927", ad="Gizem", soyad="Koç", hitap="Hanım", dogum_tarihi="1988-03-08", tckn_son4="1846",
         kartlar=[_card("KRT-240927-01", "2051", 3985.50, 1594.20, "2026-10-12", 9)], test_notu=""),
    dict(musteri_no="FB-241142", ad="Deniz", soyad="Aksoy", hitap="Hanım", dogum_tarihi="1993-05-19", tckn_son4="8076",
         kartlar=[_card("KRT-241142-01", "3608", 7260.25, 2904.10, "2026-10-19", 3)], test_notu=""),
    dict(musteri_no="FB-241250", ad="Emre", soyad="Polat", hitap="Bey", dogum_tarihi="1968-09-12", tckn_son4="4925",
         kartlar=[_card("KRT-241250-01", "5124", 9875.00, 3950.00, "2026-09-07", 44)], test_notu=""),
]
BY_ID = {c["musteri_no"]: c for c in CUSTOMERS}

# contract code -> kit system value (what a correct build's semantics are)
OUTCOMES = {"SOZ_ALINDI": "promise", "ODEME_YAPILMIS": "paid", "AKTARILDI": "transferred",
            "SOZ_ALINAMADI": "no_promise", "DOGRULANAMADI": "not_verified", "ULASILAMADI": "not_reached"}
REASONS = {"REDDETTI": "refused", "ZOR_DURUM": "hardship", "ITIRAZ": "dispute", "SISTEM_HATASI": "service_error",
           "HATALI_CEVAP": "failed", "CEVAP_VERMEDI": "declined", "GERI_ARAMA": "callback",
           "GERI_ARAMA_YOK": "no_callback", "YANLIS_NUMARA": "wrong_number", "VEFAT": "deceased",
           "BELIRSIZ": "unclear", "FINANSAL_DESTEK": "support", "YAPILANDIRMA": "restructuring", "TEMSILCI": "human"}
QUEUES = {"FINANSAL_DESTEK": "support", "YAPILANDIRMA": "restructuring", "MUSTERI_TEMSILCISI": "general"}
NOTE_TYPES = {"ODENDI_BEYANI": "paid", "ITIRAZ": "dispute"}
# allowed (sonuc_kodu, gerekce_kodu) pairs -- the closing table of the contract, section 9
CLOSE_TABLE = [
    ("SOZ_ALINDI", None, "En az bir kart için ödeme sözü kaydedildi."),
    ("ODEME_YAPILMIS", None, "Müşteri gecikmiş ekstre borcunu zaten ödediğini söyledi (tüm kartlar)."),
    ("AKTARILDI", "FINANSAL_DESTEK", "Zor durumdaki müşteri Finansal Destek Ekibine aktarıldı."),
    ("AKTARILDI", "YAPILANDIRMA", "Yapılandırma / taksitlendirme isteği; Yapılandırma Ekibine aktarıldı."),
    ("AKTARILDI", "TEMSILCI", "Müşteri ısrarla bir temsilci istedi; aktarıldı."),
    ("SOZ_ALINAMADI", "REDDETTI", "İkna denemeleri bitti veya müşteri konuşmak istemedi."),
    ("SOZ_ALINAMADI", "ZOR_DURUM", "Zor durum; müşteri aktarımı kabul etmedi."),
    ("SOZ_ALINAMADI", "ITIRAZ", "Müşteri borca / harcamaya itiraz etti."),
    ("SOZ_ALINAMADI", "SISTEM_HATASI", "OdemeSozuKaydet iki denemede de başarısız oldu."),
    ("DOGRULANAMADI", "HATALI_CEVAP", "Toplam üç yanlış cevap."),
    ("DOGRULANAMADI", "CEVAP_VERMEDI", "Müşteri güvenlik sorularını cevaplamak istemedi."),
    ("ULASILAMADI", "GERI_ARAMA", "Telefonu başkası açtı; geri arama planlandı."),
    ("ULASILAMADI", "GERI_ARAMA_YOK", "Telefonu başkası açtı; uygun saat bulunamadı."),
    ("ULASILAMADI", "YANLIS_NUMARA", "Numara müşteriye ait değil."),
    ("ULASILAMADI", "VEFAT", "Müşterinin vefat ettiği söylendi."),
    ("ULASILAMADI", "BELIRSIZ", "İki sorudan sonra hattaki kişi teyit edilemedi."),
]

OPENING = "Merhaba, ben Freya Bank'ın dijital asistanıyım. Bu görüşme kalite amacıyla kayıt altına alınmaktadır."
FIRST_ASK = "Bu ödemeyi bugün yapabilir misiniz?"
CONFIRM_Q = "Onaylıyor musunuz?"
SMS = "Bu ödeme sözünü onaylayan bir SMS alacaksınız."
REST_OVERDUE = "Kalan tutar gecikmede kalmaya devam eder."
SCAM = "Bu aramayı Freya Bank müşteri hizmetleri numarasını arayarak doğrulayabilirsiniz."
ROBOT = "Freya Bank'ın dijital asistanıyım."
SORRY_LOSS = "Başınız sağ olsun."
GET_WELL = "Geçmiş olsun."
PAID_DELAY = "Ödemelerin sisteme yansıması bir iş günü sürebilir."
GOODBYE = "Zaman ayırdığınız için teşekkür ederim, iyi günler dilerim."
BANNED_BEFORE_VERIFICATION = ["borç", "ekstre", "ödeme", "kredi kartı", "kart", "gecikme", "tahsilat", "asgari",
                              "tutar", "faiz"]
NEVER_OFFER = ["faiz indirimi", "borç silme", "taksitlendirme", "yapılandırma", "erteleme"]
NEVER_ASK = ["Ne kadar ödeyebilirsiniz?"]


# ---------------------------------------------------------------- conversations
def _ok(**kw):
    return dict(basarili=True, **kw)


def _id_ok(left, done):
    return _ok(dogrulandi=True, kalan_hak=left, tum_sorular_tamam=done)


def _id_bad(left):
    return _ok(dogrulandi=False, kalan_hak=left, tum_sorular_tamam=False)


def _stmt(c):
    return _ok(kartlar=c["kartlar"])


def _intro(c, card, first=True):
    gd = d(card["son_odeme_tarihi"])
    pre = f"Teşekkür ederim {c['ad']} {c['hitap']}. Freya Bank tahsilat biriminden arıyorum. " if first else ""
    return (pre + f"{card['kart_son4']} ile biten kredi kartınızın ekstre borcu {tl(card['ekstre_borcu'])}; son ödeme "
            f"tarihi {tr_date(gd, weekday=False, year=False)} idi ve ödeme {card['gecikme_gun_sayisi']} gündür "
            f"gecikmede. {FIRST_ASK}")


def _confirm(card, amount, day):
    return (f"Özetliyorum: {card['kart_son4']} ile biten kredi kartınız için {tl(amount)}, ödeme tarihi {tr_date(day)}. "
            f"{CONFIRM_Q}")


def _verify(cid, q, ans):
    return dict(musteri_no=cid, soru=q, cevap=ans)


def _promise_body(c, card, amount, day, tip):
    return dict(musteri_no=c["musteri_no"], kart_id=card["kart_id"], tutar=amount, odeme_tarihi=day.isoformat(),
                soz_tipi=tip)


def _close(cid, code, reason=None):
    b = dict(musteri_no=cid, sonuc_kodu=code)
    if reason:
        b["gerekce_kodu"] = reason
    return b


def _rp(c):
    return f"{c['ad']} {c['soyad']} ile mi görüşüyorum?"


def conversations():
    """13 cases. Each: id, ornek (example file number or None), title, family, now, musteri_no, variables, turns.
    turns: ("A", text) agent | ("M", text) customer/relative | ("S", op, body, response, http_status)."""
    out = []

    def V(c, now):
        return dict(musteri_no=c["musteri_no"], ad=c["ad"], soyad=c["soyad"], hitap=c["hitap"], now=now)

    # ---- TRF-01 / örnek 1: full statement debt today
    c = BY_ID["FB-240117"]; k = c["kartlar"][0]; now = "2026-10-21T10:30"; t = d(now)
    out.append(dict(id="TRF-01", ornek=1, family="Mutlu yol", title="Ekstre borcunun tamamı bugün", now=now,
                    musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Evet, benim."),
        ("A", "Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?"),
        ("M", "On dört Şubat seksen altı."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "14.02.1986"), _id_ok(3, False), 200),
        ("A", "Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?"),
        ("M", "Üç sıfır beş sekiz."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "TCKN_SON4", "3058"), _id_ok(3, True), 200),
        ("S", "EkstreBorcSorgula", dict(musteri_no=c["musteri_no"]), _stmt(c), 200),
        ("A", _intro(c, k)),
        ("M", "Evet, bugün tamamını yatırırım."),
        ("A", _confirm(k, k["ekstre_borcu"], t)),
        ("M", "Evet, onaylıyorum."),
        ("S", "OdemeSozuKaydet", _promise_body(c, k, k["ekstre_borcu"], t, "TAMAMI"), _ok(soz_no="SZ-1001"), 200),
        ("A", f"Ödeme sözünüz kaydedildi. {SMS} Başka bir sorunuz var mı?"),
        ("M", "Yok, teşekkürler."),
        ("A", GOODBYE),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "SOZ_ALINDI"), _ok(), 200),
    ]))

    # ---- TRF-02 / örnek 2: too much -> minimum; customer names the 29 Oct holiday -> next business day 30 Oct
    c = BY_ID["FB-240233"]; k = c["kartlar"][0]; now = "2026-10-27T14:00"; t = d(now)
    hol = d("2026-10-29"); nxt = next_bd_on_or_after(hol)
    assert deadline(now, k["gecikme_gun_sayisi"]) == d("2026-11-02") and nxt == d("2026-10-30")
    out.append(dict(id="TRF-02", ornek=2, family="Asgari ödeme + tatil", title="Asgari ödeme; 29 Ekim tatil, 30 Ekim önerilir",
                    now=now, musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Buyurun."),
        ("A", f"Kusura bakmayın, {_rp(c)}"),
        ("M", "Evet, Mehmet Kaya benim."),
        ("A", "Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?"),
        ("M", "Üç Ocak bin dokuz yüz seksen beş."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "03.01.1985"), _id_ok(3, False), 200),
        ("A", "Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?"),
        ("M", "Altı altı bir dört."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "TCKN_SON4", "6614"), _id_ok(3, True), 200),
        ("S", "EkstreBorcSorgula", dict(musteri_no=c["musteri_no"]), _stmt(c), 200),
        ("A", _intro(c, k)),
        ("M", "Bugün olmaz, hem tamamı benim için çok fazla."),
        ("A", f"Anlıyorum. O halde asgari ödeme tutarı olan {tl(k['asgari_odeme_tutari'])} ödenebilir. {REST_OVERDUE} "
              f"Bu tutarı hangi gün ödeyebilirsiniz?"),
        ("M", "Asgariyi 29 Ekim'de yatırırım."),
        ("A", f"29 Ekim resmi tatil. Bir sonraki iş günü olan {tr_date(nxt)} günü ödeyebilir misiniz?"),
        ("M", "Olur, cuma yatırırım."),
        ("A", _confirm(k, k["asgari_odeme_tutari"], nxt)),
        ("M", "Evet."),
        ("S", "OdemeSozuKaydet", _promise_body(c, k, k["asgari_odeme_tutari"], nxt, "ASGARI"), _ok(soz_no="SZ-1002"), 200),
        ("A", f"Ödeme sözünüz kaydedildi. {SMS}"),
        ("M", "Tamam, sağ olun."),
        ("A", GOODBYE),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "SOZ_ALINDI"), _ok(), 200),
    ]))

    # ---- TRF-03 / örnek 3: spouse answers; asks evening of the arife day -> 09:00-12:30 only -> 11:00
    c = BY_ID["FB-240318"]; now = "2026-10-27T17:15"
    cb = d("2026-10-28")
    assert callback_windows(now, cb) == [("09:00", "12:30")]
    out.append(dict(id="TRF-03", ornek=3, family="Üçüncü kişi", title="Eşi açıyor; arife günü akşamı yerine sabah geri arama",
                    now=now, musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Ben eşiyim, Zeynep şu an müsait değil. Ne için aramıştınız?"),
        ("A", f"Bunu yalnızca {c['ad']} {c['hitap']} ile görüşebilirim. {c['ad']} {c['hitap']}'a ne zaman ulaşabiliriz?"),
        ("M", "Bir ödeme meselesiyse ben hallederim, söyleyin."),
        ("A", f"Teşekkür ederim, ancak bu konuyu yalnızca {c['ad']} {c['hitap']} ile görüşebilirim. Ne zaman aramamız uygun olur?"),
        ("M", "Yarın akşam yedi gibi arayın."),
        ("A", "Yarın arife olduğu için yalnızca 09:00 ile 12:30 arasında arayabiliyoruz; bugün de saat 20:00'ye kadar "
              "arayabiliriz. Bu saatlerden biri uygun olur mu?"),
        ("M", "O zaman yarın sabah on bir olsun."),
        ("S", "GeriAramaPlanla", dict(musteri_no=c["musteri_no"], tarih="2026-10-28", saat="11:00"), _ok(randevu_no="GA-2001"), 200),
        ("A", f"Teşekkür ederim. {c['ad']} {c['hitap']}'ı {tr_date(cb)} saat 11:00'de arayacağız. İyi akşamlar dilerim."),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "ULASILAMADI", "GERI_ARAMA"), _ok(), 200),
    ]))

    # ---- TRF-04 / örnek 4: day/month swapped hint, then 'already paid'
    c = BY_ID["FB-240402"]; k = c["kartlar"][0]; now = "2026-10-22T11:00"
    out.append(dict(id="TRF-04", ornek=4, family="Kimlik + zaten ödedim", title="Gün-ay ters ipucu; sonra 'dün ödedim'",
                    now=now, musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Benim, buyurun."),
        ("A", "Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?"),
        ("M", "Dört dokuz yetmiş dokuz."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "04.09.1979"),
         _ok(dogrulandi=False, kalan_hak=3, tum_sorular_tamam=False, ipucu="GUN_AY_YER_DEGISTI"), 200),
        ("A", "Doğum tarihinizi ayın adıyla söyler misiniz? Örneğin on beş Mart gibi."),
        ("M", "Dokuz Nisan bin dokuz yüz yetmiş dokuz."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "09.04.1979"), _id_ok(3, False), 200),
        ("A", "Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?"),
        ("M", "Dokuz bir iki yedi."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "TCKN_SON4", "9127"), _id_ok(3, True), 200),
        ("S", "EkstreBorcSorgula", dict(musteri_no=c["musteri_no"]), _stmt(c), 200),
        ("A", _intro(c, k)),
        ("M", "Ben onu dün internet bankacılığından ödedim ama."),
        ("A", f"{PAID_DELAY} Bilginizi not alıyorum."),
        ("S", "NotEkle", dict(musteri_no=c["musteri_no"], kart_id=k["kart_id"], not_tipi="ODENDI_BEYANI",
                              aciklama="Müşteri ekstre borcunu 21.10.2026 tarihinde internet bankacılığından ödediğini belirtti."),
         _ok(not_no="NT-3001"), 200),
        ("M", "Tamam."),
        ("A", GOODBYE),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "ODEME_YAPILMIS"), _ok(), 200),
    ]))

    # ---- TRF-05 / örnek 5: robot question; job loss -> Finansal Destek transfer accepted
    c = BY_ID["FB-240561"]; now = "2026-10-21T15:00"; k = c["kartlar"][0]
    out.append(dict(id="TRF-05", ornek=5, family="Zor durum", title="Robot sorusu; iş kaybı, Finansal Destek'e aktarım",
                    now=now, musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Siz robot musunuz?"),
        ("A", f"{ROBOT} {_rp(c)}"),
        ("M", "Evet, benim."),
        ("A", "Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?"),
        ("M", "Otuz Kasım doksan."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "30.11.1990"), _id_ok(3, False), 200),
        ("A", "Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?"),
        ("M", "Sıfır iki sekiz beş."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "TCKN_SON4", "0285"), _id_ok(3, True), 200),
        ("S", "EkstreBorcSorgula", dict(musteri_no=c["musteri_no"]), _stmt(c), 200),
        ("A", _intro(c, k)),
        ("M", "Bugün ödeyemem. Geçen ay işten çıkarıldım, şu an hiç gelirim yok."),
        ("A", f"{GET_WELL} İsterseniz sizi Finansal Destek Ekibimize aktarabilirim; durumunuza uygun seçenekleri onlar "
              f"değerlendirir. Aktarmamı ister misiniz?"),
        ("M", "Evet, lütfen."),
        ("S", "CagriAktar", dict(musteri_no=c["musteri_no"], kuyruk="FINANSAL_DESTEK"), _ok(), 200),
        ("A", f"Sizi şimdi Finansal Destek Ekibimize aktarıyorum. {GOODBYE}"),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "AKTARILDI", "FINANSAL_DESTEK"), _ok(), 200),
    ]))

    # ---- TRF-06 / örnek 6: scam question; two cards; DUY-2026-034 (geç band -> 2nd business day) in force
    c = BY_ID["FB-240699"]; k1, k2 = c["kartlar"]; now = "2026-11-03T10:00"; t = d(now)
    dl = deadline(now, k1["gecikme_gun_sayisi"]); a1 = min(last_bd_of_week(t), dl)
    assert dl == d("2026-11-05") and a1 == d("2026-11-05") and last_bd_of_week(t) == d("2026-11-06")
    out.append(dict(id="TRF-06", ornek=6, family="İki kart + duyuru", title="Dolandırıcılık sorusu; iki kart: biri söz (son tarih), biri itiraz",
                    now=now, musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Bu bir dolandırıcılık olmasın?"),
        ("A", f"{SCAM} {_rp(c)}"),
        ("M", "Evet benim."),
        ("A", "Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?"),
        ("M", "İki altı seksen üç."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "02.06.1983"), _id_ok(3, False), 200),
        ("A", "Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?"),
        ("M", "Yedi yedi beş bir."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "TCKN_SON4", "7751"), _id_ok(3, True), 200),
        ("S", "EkstreBorcSorgula", dict(musteri_no=c["musteri_no"]), _stmt(c), 200),
        ("A", f"Teşekkür ederim {c['ad']} {c['hitap']}. Freya Bank tahsilat biriminden arıyorum. İki kredi kartınızda "
              f"gecikme var; önce en çok geciken kartla başlayacağım. " + _intro(c, k1, first=False)),
        ("M", "Bugün olmaz."),
        ("A", f"{tl(k1['ekstre_borcu'])} tutarın tamamını {tr_date(a1)} günü ödeyebilir misiniz?"),
        ("M", "Tamam, perşembe öderim."),
        ("A", _confirm(k1, k1["ekstre_borcu"], a1)),
        ("M", "Evet, onaylıyorum."),
        ("S", "OdemeSozuKaydet", _promise_body(c, k1, k1["ekstre_borcu"], a1, "TAMAMI"), _ok(soz_no="SZ-1006"), 200),
        ("A", f"Ödeme sözünüz kaydedildi. {SMS} Bir de " + _intro(c, k2, first=False)),
        ("M", "O karttaki harcamaları ben yapmadım, bankaya itiraz ettim zaten."),
        ("A", "Anlıyorum, itirazınızı not alıyorum."),
        ("S", "NotEkle", dict(musteri_no=c["musteri_no"], kart_id=k2["kart_id"], not_tipi="ITIRAZ",
                              aciklama="Müşteri 1187 ile biten karttaki harcamaları kendisinin yapmadığını ve itiraz ettiğini söyledi."),
         _ok(not_no="NT-3006"), 200),
        ("A", GOODBYE),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "SOZ_ALINDI"), _ok(), 200),
    ]))

    # ---- TRF-07: create fails twice -> SISTEM_HATASI, never says "kaydedildi"
    c = BY_ID["FB-240744"]; k = c["kartlar"][0]; now = "2026-10-21T11:30"; t = d(now)
    err = dict(basarili=False, hata_kodu="E500")
    out.append(dict(id="TRF-07", ornek=None, family="Servis hatası", title="Söz kaydı iki kez başarısız",
                    now=now, musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Evet, benim."),
        ("A", "Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?"),
        ("M", "Dört Ağustos doksan beş."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "04.08.1995"), _id_ok(3, False), 200),
        ("A", "Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?"),
        ("M", "Beş beş üç sıfır."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "TCKN_SON4", "5530"), _id_ok(3, True), 200),
        ("S", "EkstreBorcSorgula", dict(musteri_no=c["musteri_no"]), _stmt(c), 200),
        ("A", _intro(c, k)),
        ("M", "Evet, bugün tamamını öderim."),
        ("A", _confirm(k, k["ekstre_borcu"], t)),
        ("M", "Evet."),
        ("S", "OdemeSozuKaydet", _promise_body(c, k, k["ekstre_borcu"], t, "TAMAMI"), err, 500),
        ("S", "OdemeSozuKaydet", _promise_body(c, k, k["ekstre_borcu"], t, "TAMAMI"), err, 500),
        ("A", "Üzgünüm, şu anda sözünüzü sisteme kaydedemedim. Ödemenizi mobil uygulamamızdan yapabilirsiniz."),
        ("M", "Peki."),
        ("A", GOODBYE),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "SOZ_ALINAMADI", "SISTEM_HATASI"), _ok(), 200),
    ]))

    # ---- TRF-08: three wrong answers -> DOGRULANAMADI / HATALI_CEVAP (none is the swapped date 03.08.1988)
    c = BY_ID["FB-240927"]; now = "2026-10-21T12:00"
    out.append(dict(id="TRF-08", ornek=None, family="Kimlik", title="Üç yanlış cevap",
                    now=now, musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Evet."),
        ("A", "Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?"),
        ("M", "Beş Mart seksen sekiz."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "05.03.1988"), _id_bad(2), 200),
        ("A", "Bu bilgi kayıtlarımızla eşleşmedi. Doğum tarihinizi tekrar söyler misiniz?"),
        ("M", "Yedi Mart seksen sekiz."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "07.03.1988"), _id_bad(1), 200),
        ("A", "Bu bilgi de eşleşmedi. Doğum tarihinizi bir kez daha söyler misiniz?"),
        ("M", "On sekiz Mart seksen sekiz o zaman."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "18.03.1988"), _id_bad(0), 200),
        ("A", "Üzgünüm, kimliğinizi doğrulayamadım. Mobil uygulamamızdan veya bir şubemizden destek alabilirsiniz. "
              + GOODBYE),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "DOGRULANAMADI", "HATALI_CEVAP"), _ok(), 200),
    ]))

    # ---- TRF-09: erken band, one persuasion attempt, refused -> REDDETTI
    c = BY_ID["FB-240927"]; k = c["kartlar"][0]; now = "2026-10-21T16:00"; t = d(now)
    a1 = min(last_bd_of_week(t), deadline(now, k["gecikme_gun_sayisi"]))
    assert a1 == d("2026-10-23")
    out.append(dict(id="TRF-09", ornek=None, family="Ret", title="Erken bant: tek ikna denemesi, ret",
                    now=now, musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Evet benim."),
        ("A", "Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?"),
        ("M", "Sekiz Mart seksen sekiz."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "08.03.1988"), _id_ok(3, False), 200),
        ("A", "Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?"),
        ("M", "Bir sekiz dört altı."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "TCKN_SON4", "1846"), _id_ok(3, True), 200),
        ("S", "EkstreBorcSorgula", dict(musteri_no=c["musteri_no"]), _stmt(c), 200),
        ("A", _intro(c, k)),
        ("M", "Hayır, bugün olmaz."),
        ("A", f"{tl(k['ekstre_borcu'])} tutarın tamamını {tr_date(a1)} günü ödeyebilir misiniz?"),
        ("M", "Hayır, o da olmaz."),
        ("A", "Anlıyorum. " + GOODBYE),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "SOZ_ALINAMADI", "REDDETTI"), _ok(), 200),
    ]))

    # ---- TRF-10: restructuring request -> transfer YAPILANDIRMA
    c = BY_ID["FB-240233"]; k = c["kartlar"][0]; now = "2026-10-27T15:30"
    out.append(dict(id="TRF-10", ornek=None, family="Yapılandırma", title="Taksitlendirme isteği, Yapılandırma Ekibine aktarım",
                    now=now, musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Evet, benim."),
        ("A", "Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?"),
        ("M", "Üç bir seksen beş."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "03.01.1985"), _id_ok(3, False), 200),
        ("A", "Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?"),
        ("M", "6614."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "TCKN_SON4", "6614"), _id_ok(3, True), 200),
        ("S", "EkstreBorcSorgula", dict(musteri_no=c["musteri_no"]), _stmt(c), 200),
        ("A", _intro(c, k)),
        ("M", "Bunu taksitlendirebilir miyiz? Borcumu yapılandırmak istiyorum."),
        ("A", "Bu konuda sizi Yapılandırma Ekibimize aktarıyorum."),
        ("S", "CagriAktar", dict(musteri_no=c["musteri_no"], kuyruk="YAPILANDIRMA"), _ok(), 200),
        ("A", GOODBYE),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "AKTARILDI", "YAPILANDIRMA"), _ok(), 200),
    ]))

    # ---- TRF-11: "gelecek çarşamba" (= arife 28 Oct, a business day) and an amount below the minimum
    c = BY_ID["FB-241142"]; k = c["kartlar"][0]; now = "2026-10-22T09:45"
    wed = d("2026-10-28")
    assert is_bd(wed) and wed <= deadline(now, k["gecikme_gun_sayisi"]) == d("2026-11-03")
    out.append(dict(id="TRF-11", ornek=None, family="Tarih + tutar", title="'Gelecek çarşamba' (arife, iş günü) ve asgarinin altında tutar",
                    now=now, musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Evet, Deniz Aksoy."),
        ("A", "Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?"),
        ("M", "On dokuz Mayıs doksan üç."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "19.05.1993"), _id_ok(3, False), 200),
        ("A", "Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?"),
        ("M", "Sekiz sıfır yedi altı."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "TCKN_SON4", "8076"), _id_ok(3, True), 200),
        ("S", "EkstreBorcSorgula", dict(musteri_no=c["musteri_no"]), _stmt(c), 200),
        ("A", _intro(c, k)),
        ("M", "Bugün olmaz ama gelecek çarşamba iki bin lira yatırabilirim."),
        ("A", f"2.000,00 TL'yi kaydedemiyorum; asgari ödeme tutarı {tl(k['asgari_odeme_tutari'])}. Bu tutarı "
              f"{tr_date(wed)} günü ödeyebilir misiniz?"),
        ("M", "Tamam, asgariyi öderim."),
        ("A", _confirm(k, k["asgari_odeme_tutari"], wed)),
        ("M", "Evet."),
        ("S", "OdemeSozuKaydet", _promise_body(c, k, k["asgari_odeme_tutari"], wed, "ASGARI"), _ok(soz_no="SZ-1011"), 200),
        ("A", f"Ödeme sözünüz kaydedildi. {SMS}"),
        ("A", GOODBYE),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "SOZ_ALINDI"), _ok(), 200),
    ]))

    # ---- TRF-12: date after the deadline -> offer the deadline (geç band, 3rd business day before DUY-2026-034)
    c = BY_ID["FB-241250"]; k = c["kartlar"][0]; now = "2026-10-21T13:00"
    dl = deadline(now, k["gecikme_gun_sayisi"])
    assert dl == d("2026-10-26")
    out.append(dict(id="TRF-12", ornek=None, family="Son tarih", title="Son tarihten sonraki gün istenir; son tarih önerilir",
                    now=now, musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Benim."),
        ("A", "Teşekkürler. Güvenliğiniz için iki soru soracağım. Önce doğum tarihinizi söyler misiniz?"),
        ("M", "On iki Eylül altmış sekiz."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "DOGUM_TARIHI", "12.09.1968"), _id_ok(3, False), 200),
        ("A", "Teşekkürler. T.C. kimlik numaranızın son dört hanesini söyler misiniz?"),
        ("M", "Dört dokuz iki beş."),
        ("S", "KimlikDogrula", _verify(c["musteri_no"], "TCKN_SON4", "4925"), _id_ok(3, True), 200),
        ("S", "EkstreBorcSorgula", dict(musteri_no=c["musteri_no"]), _stmt(c), 200),
        ("A", _intro(c, k)),
        ("M", "Bugün olmaz. Ay sonunda, 30 Ekim'de tamamını öderim."),
        ("A", f"Kaydedebileceğim en geç tarih {tr_date(dl)}. Tutarın tamamını o gün ödeyebilir misiniz?"),
        ("M", "Peki, 26'sında öderim."),
        ("A", _confirm(k, k["ekstre_borcu"], dl)),
        ("M", "Evet."),
        ("S", "OdemeSozuKaydet", _promise_body(c, k, k["ekstre_borcu"], dl, "TAMAMI"), _ok(soz_no="SZ-1012"), 200),
        ("A", f"Ödeme sözünüz kaydedildi. {SMS}"),
        ("A", GOODBYE),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "SOZ_ALINDI"), _ok(), 200),
    ]))

    # ---- TRF-13: son answers; 19:30 today is inside the DUY-2026-031 window (09:00-20:00), outside the BRIEF's 18:00
    c = BY_ID["FB-241250"]; now = "2026-10-21T11:00"
    assert callback_windows(now, d(now)) == [("09:00", "20:00")]
    out.append(dict(id="TRF-13", ornek=None, family="Üçüncü kişi + duyuru", title="Oğlu açıyor; bugün 19:30 geri arama (genişletilmiş saat)",
                    now=now, musteri_no=c["musteri_no"], variables=V(c, now), turns=[
        ("A", f"{OPENING} {_rp(c)}"),
        ("M", "Ben oğluyum, babam şu an evde değil."),
        ("A", f"{c['ad']} {c['hitap']}'e ne zaman ulaşabiliriz?"),
        ("M", "Bu akşam yedi buçukta evde olur."),
        ("S", "GeriAramaPlanla", dict(musteri_no=c["musteri_no"], tarih="2026-10-21", saat="19:30"), _ok(randevu_no="GA-2013"), 200),
        ("A", f"Teşekkür ederim. {c['ad']} {c['hitap']}'i bugün saat 19:30'da arayacağız. İyi günler dilerim."),
        ("S", "GorusmeKapat", _close(c["musteri_no"], "ULASILAMADI", "GERI_ARAMA"), _ok(), 200),
    ]))
    return out


WRITE_OPS = ("OdemeSozuKaydet", "GeriAramaPlanla", "CagriAktar", "NotEkle", "GorusmeKapat")


def ledger(conv):
    """Successful write calls, in order (what the mock ledger must hold at the end)."""
    return [dict(op=t[1], body=t[2]) for t in conv["turns"]
            if t[0] == "S" and t[1] in WRITE_OPS and t[3].get("basarili") and t[4] == 200]
