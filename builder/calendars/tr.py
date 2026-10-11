"""Türkiye public holidays (resmi tatiller), 2026-2027, from the official calendars (Diyanet for the two Eids).

Full days are not business days. Half days (arife and 28 October from 13:00) are listed separately;
by default they remain business days unless a brief says otherwise. Government "idari izin" bridge days
are announced ad hoc and must come from the bank's own announcements.
"""

_FIXED = ("01-01", "04-23", "05-01", "05-19", "07-15", "08-30", "10-29")

_EIDS_FULL = {
    2026: ("2026-03-20", "2026-03-21", "2026-03-22",                 # Ramazan Bayramı
           "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30"),  # Kurban Bayramı
    2027: ("2027-03-09", "2027-03-10", "2027-03-11",
           "2027-05-16", "2027-05-17", "2027-05-18", "2027-05-19"),
}
_EIDS_HALF = {
    2026: ("2026-03-19", "2026-05-26"),
    2027: ("2027-03-08", "2027-05-15"),
}

TR_FULL_DAYS = tuple(sorted({f"{y}-{md}" for y in _EIDS_FULL for md in _FIXED}
                            | {d for days in _EIDS_FULL.values() for d in days}))
TR_HALF_DAYS = tuple(sorted({f"{y}-10-28" for y in _EIDS_FULL} | {d for days in _EIDS_HALF.values() for d in days}))
