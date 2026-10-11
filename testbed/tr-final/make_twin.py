"""Write testbed/tr-final/twin/TRF-xx.json (twin scenarios) from cases.json plus hand-written extractor values. Run: .venv/bin/python testbed/tr-final/make_twin.py"""
import datetime
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = REPO / "testbed/tr-final/twin"
CASES = {c["id"]: c for c in json.loads((REPO / "testbed/tr-final/cases.json").read_text())}

FAULT_TOOL = {"OdemeSozuKaydet": "create_promise", "KimlikDogrula": "verify_identity",
              "EkstreBorcSorgula": "get_account", "NotEkle": "add_note", "GeriAramaPlanla": "schedule_callback",
              "CagriAktar": "transfer_to_agent", "GorusmeKapat": "close_call"}


def T(say, en, act, topic="none", **kw):
    x = {"u_text": say, "u_en": en, "u_act": act, "u_topic": topic}
    x.update(kw)
    return {"say": say, "x": x}


def ID(say, en, val, done="complete", act="answer", topic="none"):
    return T(say, en, act, topic, u_val=val, u_done=done)


def N(say, en, act, kind, topic="none", amt="", dkind="none", dval="", dwhich="bare", **kw):
    """neg / conf stage sensors (also valid at s_tp/s_rp: extra names are ignored by the twin)."""
    return T(say, en, act, topic, u_amt=amt, u_dkind=dkind, u_dval=dval, u_dwhich=dwhich, u_kind=kind, **kw)


def due_dates(case):
    out = {}
    for sc in case.get("service_calls") or []:
        if sc["op"] == "EkstreBorcSorgula":
            for k in (sc.get("response") or {}).get("kartlar") or []:
                out[k["kart_id"]] = k.get("son_odeme_tarihi")
    return out


def products(case):
    dd = due_dates(case)
    now = datetime.date.fromisoformat(case["variables"]["now"][:10])
    rows = []
    for p in case["products"]:
        rows.append({"kart_id": p["product_id"], "urun": "KREDI_KARTI", "kart_son4": p["card_last4"],
                     "ekstre_borcu": p["past_due"], "asgari_odeme_tutari": p["minimum_payment"],
                     "son_odeme_tarihi": dd.get(p["product_id"]) or (now - datetime.timedelta(days=p["days_late"])).isoformat(),
                     "gecikme_gun_sayisi": p["days_late"]})
    return rows


def expect(case):
    e = {"outcome": None, "reason": None, "promises": [], "notes": [], "callbacks": [], "transfers": []}
    for c in case["expected_ledger"]:
        b = c["body"]
        if c["op"] == "OdemeSozuKaydet":
            e["promises"].append({"product_id": b["kart_id"], "amount": b["tutar"], "date": b["odeme_tarihi"]})
        elif c["op"] == "NotEkle":
            e["notes"].append({"product_id": b.get("kart_id"), "reason": b["not_tipi"]})
        elif c["op"] == "CagriAktar":
            e["transfers"].append({"queue": b["kuyruk"]})
        elif c["op"] == "GeriAramaPlanla":
            e["callbacks"].append({"date": b["tarih"], "time": b["saat"]})
        elif c["op"] == "GorusmeKapat":
            e["outcome"] = b["sonuc_kodu"]
            e["reason"] = b.get("gerekce_kodu")
    return e


def faults(case):
    out = []
    for op, mode in (case.get("faults") or {}).items():
        # E500 on every call of that op (the case says the service keeps failing)
        out.append({"tool": FAULT_TOOL[op], "fail_first_n": 9, "mode": "http500" if str(mode).startswith("E5") else "ok_false"})
    return out


TURNS = {
    "TRF-01": [
        T("Evet, benim.", "Yes, it's me.", "yes"),
        ID("On dört Şubat seksen altı.", "Fourteenth of February, eighty-six.", "1986-02-14"),
        ID("Üç sıfır beş sekiz.", "Three zero five eight.", "3058"),
        N("Evet, bugün tamamını yatırırım.", "Yes, I'll pay all of it today.", "yes", "yes",
          dkind="relative_days", dval="0"),
        N("Evet, onaylıyorum.", "Yes, I confirm.", "yes", "yes"),
        N("Yok, teşekkürler.", "No, thanks.", "no", "no"),
    ],
    "TRF-02": [
        T("Buyurun.", "Go ahead.", "chatter_only"),
        T("Evet, Mehmet Kaya benim.", "Yes, I'm Mehmet Kaya.", "yes"),
        ID("Üç Ocak bin dokuz yüz seksen beş.", "Third of January, nineteen eighty-five.", "1985-01-03"),
        ID("Altı altı bir dört.", "Six six one four.", "6614"),
        N("Bugün olmaz, hem tamamı benim için çok fazla.", "Not today, and the full amount is too much for me.",
          "no", "no", topic="full_too_much"),
        N("Asgariyi 29 Ekim'de yatırırım.", "I'll pay the minimum on 29 October.", "proposal", "answer",
          dkind="absolute", dval="10-29"),
        N("Olur, cuma yatırırım.", "Okay, I'll pay on Friday.", "yes", "yes", dkind="weekday", dval="Friday"),
        N("Evet.", "Yes.", "yes", "yes"),
        N("Tamam, sağ olun.", "Okay, thank you.", "chatter_only", "smalltalk"),
    ],
    "TRF-03": [
        T("Ben eşiyim, Zeynep şu an müsait değil. Ne için aramıştınız?",
          "I'm her husband, Zeynep isn't available right now. What were you calling about?", "no", "other_person",
          u_date="", u_time=""),
        T("Bir ödeme meselesiyse ben hallederim, söyleyin.", "If it's a payment matter I'll handle it, tell me.",
          "question", "third_party_asks_or_offers", u_date="", u_time=""),
        T("Yarın akşam yedi gibi arayın.", "Call tomorrow evening around seven.", "proposal",
          u_date="tomorrow", u_time="around seven in the evening"),
        T("O zaman yarın sabah on bir olsun.", "Then let's make it tomorrow morning at eleven.", "proposal",
          u_date="tomorrow", u_time="eleven in the morning"),
    ],
    "TRF-04": [
        T("Benim, buyurun.", "It's me, go ahead.", "yes"),
        # MockBank cannot answer the GUN_AY_YER_DEGISTI hint for a GG.AA.YYYY identity value (hint needs an ISO
        # value), so the swapped answer is a counted wrong answer here; the ledger is unaffected
        ID("Dört dokuz yetmiş dokuz.", "Four nine seventy-nine.", "1979-09-04"),
        ID("Dokuz Nisan bin dokuz yüz yetmiş dokuz.", "Ninth of April, nineteen seventy-nine.", "1979-04-09"),
        ID("Dokuz bir iki yedi.", "Nine one two seven.", "9127"),
        N("Ben onu dün internet bankacılığından ödedim ama.", "But I paid that yesterday through internet banking.",
          "answer", "answer", topic="already_paid"),
        N("Tamam.", "Okay.", "yes", "yes"),
    ],
    "TRF-05": [
        T("Siz robot musunuz?", "Are you a robot?", "question", "robot_question"),
        T("Evet, benim.", "Yes, it's me.", "yes"),
        ID("Otuz Kasım doksan.", "Thirtieth of November, ninety.", "1990-11-30"),
        ID("Sıfır iki sekiz beş.", "Zero two eight five.", "0285"),
        N("Bugün ödeyemem. Geçen ay işten çıkarıldım, şu an hiç gelirim yok.",
          "I can't pay today. I was laid off last month, I have no income right now.", "no", "no",
          topic="hardship_illness_job"),
        N("Evet, lütfen.", "Yes, please.", "yes", "yes"),
    ],
    "TRF-06": [
        T("Bu bir dolandırıcılık olmasın?", "This isn't a scam, is it?", "question", "scam_question"),
        T("Evet benim.", "Yes, it's me.", "yes"),
        ID("İki altı seksen üç.", "Two six eighty-three.", "1983-06-02"),
        ID("Yedi yedi beş bir.", "Seven seven five one.", "7751"),
        N("Bugün olmaz.", "Not today.", "no", "no"),
        N("Tamam, perşembe öderim.", "Okay, I'll pay on Thursday.", "yes", "yes", dkind="weekday", dval="Thursday"),
        N("Evet, onaylıyorum.", "Yes, I confirm.", "yes", "yes"),
        N("O karttaki harcamaları ben yapmadım, bankaya itiraz ettim zaten.",
          "I didn't make the charges on that card, I've already disputed them with the bank.", "answer", "answer",
          topic="dispute"),
    ],
    "TRF-07": [
        T("Evet, benim.", "Yes, it's me.", "yes"),
        ID("Dört Ağustos doksan beş.", "Fourth of August, ninety-five.", "1995-08-04"),
        ID("Beş beş üç sıfır.", "Five five three zero.", "5530"),
        N("Evet, bugün tamamını öderim.", "Yes, I'll pay all of it today.", "yes", "yes",
          dkind="relative_days", dval="0"),
        N("Evet.", "Yes.", "yes", "yes"),
        N("Peki.", "Okay.", "chatter_only", "smalltalk"),
    ],
    "TRF-08": [
        T("Evet.", "Yes.", "yes"),
        ID("Beş Mart seksen sekiz.", "Fifth of March, eighty-eight.", "1988-03-05"),
        ID("Yedi Mart seksen sekiz.", "Seventh of March, eighty-eight.", "1988-03-07"),
        ID("On sekiz Mart seksen sekiz o zaman.", "Eighteenth of March, eighty-eight then.", "1988-03-18"),
    ],
    "TRF-09": [
        T("Evet benim.", "Yes, it's me.", "yes"),
        ID("Sekiz Mart seksen sekiz.", "Eighth of March, eighty-eight.", "1988-03-08"),
        ID("Bir sekiz dört altı.", "One eight four six.", "1846"),
        N("Hayır, bugün olmaz.", "No, not today.", "no", "no"),
        N("Hayır, o da olmaz.", "No, that won't work either.", "no", "no"),
    ],
    "TRF-10": [
        T("Evet, benim.", "Yes, it's me.", "yes"),
        ID("Üç bir seksen beş.", "Three one eighty-five.", "1985-01-03"),
        ID("6614.", "6614.", "6614"),
        N("Bunu taksitlendirebilir miyiz? Borcumu yapılandırmak istiyorum.",
          "Can we split this into instalments? I want to restructure my debt.", "question", "question",
          topic="restructure_request"),
    ],
    "TRF-11": [
        T("Evet, Deniz Aksoy.", "Yes, Deniz Aksoy.", "yes"),
        ID("On dokuz Mayıs doksan üç.", "Nineteenth of May, ninety-three.", "1993-05-19"),
        ID("Sekiz sıfır yedi altı.", "Eight zero seven six.", "8076"),
        N("Bugün olmaz ama gelecek çarşamba iki bin lira yatırabilirim.",
          "Not today, but next Wednesday I can pay 2,000 lira.", "proposal", "answer", amt="2000",
          dkind="weekday", dval="Wednesday", dwhich="next"),
        N("Tamam, asgariyi öderim.", "Okay, I'll pay the minimum.", "yes", "yes"),
        N("Evet.", "Yes.", "yes", "yes"),
    ],
    "TRF-12": [
        T("Benim.", "It's me.", "yes"),
        ID("On iki Eylül altmış sekiz.", "Twelfth of September, sixty-eight.", "1968-09-12"),
        ID("Dört dokuz iki beş.", "Four nine two five.", "4925"),
        N("Bugün olmaz. Ay sonunda, 30 Ekim'de tamamını öderim.",
          "Not today. At the end of the month, on 30 October, I'll pay all of it.", "proposal", "answer",
          dkind="absolute", dval="10-30"),
        N("Peki, 26'sında öderim.", "Alright, I'll pay on the 26th.", "yes", "yes", dkind="day_of_month", dval="26"),
        N("Evet.", "Yes.", "yes", "yes"),
    ],
    "TRF-13": [
        T("Ben oğluyum, babam şu an evde değil.", "I'm his son, my father isn't home right now.", "no",
          "other_person", u_date="", u_time=""),
        T("Bu akşam yedi buçukta evde olur.", "He'll be home at half past seven this evening.", "proposal",
          u_date="this evening", u_time="half past seven in the evening"),
    ],
}


def main():
    for cid, turns in TURNS.items():
        case = CASES[cid]
        assert len(turns) == len(case["customer_lines"]), (cid, len(turns), len(case["customer_lines"]))
        for t, line in zip(turns, case["customer_lines"]):
            assert t["say"] == line, (cid, t["say"], line)
        sc = {"id": cid, "title": case["title"], "mode": "sim",
              "case": {"id": cid, "variables": case["variables"], "identity": case["identity"],
                       "products": products(case)},
              "expect": expect(case),
              "turns": turns,
              "transcript": {"no_banned_before_verified": True, "one_line_per_turn": True, "max_hops": 24}}
        f = faults(case)
        if f:
            sc["faults"] = f
        (OUT / (cid + ".json")).write_text(json.dumps(sc, ensure_ascii=False, indent=1) + "\n")
        if cid == "TRF-06":
            # the same customer raising the dispute during the 5502 read-back, naming the 1187 card: only 1187 is
            # disputed, the 5502 read-back stands and is confirmed, then nothing else
            sa = json.loads(json.dumps(sc))
            sa["id"] = "TRF-06a"
            sa["title"] = case["title"] + " (the dispute names the other card during the read-back)"
            t = sa["turns"]
            dis = json.loads(json.dumps(t[7]))
            dis["say"] = dis["x"]["u_text"] = "1187 ile biten karttaki harcamaları ben yapmadım, itiraz ettim."
            dis["x"]["u_en"] = "I didn't make the charges on the card ending 1187, I've disputed them."
            bye = {"say": "Hayır, teşekkürler.", "x": dict(t[6]["x"], u_text="Hayır, teşekkürler.",
                                                           u_en="No, thank you.", u_act="no", u_kind="no")}
            sa["turns"] = t[:6] + [dis, t[6], bye]
            (OUT / "TRF-06a.json").write_text(json.dumps(sa, ensure_ascii=False, indent=1) + "\n")
    print("wrote", len(TURNS))


if __name__ == "__main__":
    main()
