"""Brief-agnostic defaults (docs/CONTRACTS.md B.7, SYSTEM-DESIGN §5.3 with the edge-case revisions).

Data (DEFAULT_* / BUILTIN_TOPICS / DEFAULTS) is lead-owned. apply_defaults() is implemented by agent 5.
The brief's own text always wins: defaults only fill keys the extraction left missing, and every filled
JSON pointer is returned so validate.py can log it in meta.defaults_applied.
Never put a value from a specific brief here.
"""

DEFAULT_INTERPRETATION = {
    "floor_offer_date": "attempt_1",
    "decline_counting": "per_question_consecutive",
    "rp_greeting_first_turn": "reask_counts",
    "rp_question_after_last_ask": "counts_as_unclear",
    "transfer_beats_promise": True,
    "after_record": "close",
    "attempt_definition": "rungs_only",
    "refused_corrective_offer": "flat_refusal",
    "proposal_beats_too_much": True,
    "floor_ge_full": "skip_floor",
    "refuse_to_talk_requires_talk_words": True,
    "paid_requires_completed_tense": True,
    "past_closure_is_dispute": True,
    "hardship_requires_cause": True,
    "hedge_is_non_answer": True,
    "readback_no": "ask_what_to_change",
    "agreed_before_terminal": "drop",
    "text_message_sentence": "once_after_all_creates",
    "partial_today": "record_today_rest_from_attempt_1",
    "notes_timing": "before_close",
    "notes_scope": "every_product_without_promise",
    "reasonless": "omit_reason_leaf",
    "malformed_identity": "never_send_ask_rest",
    "callback_today_nonbd": "allow",
    "hedged_time": "exact",
    "weekend_now_attempt1": "last_bd_of_next_week",
    "intent_tie": [],
}

DEFAULT_LINES = {
    "clarify": "Sorry, could you say that again?",
    "no_info": "I'm sorry, I don't have that information.",
    "ack": "I understand.",
    "neutral_reask": "Would that work for you?",
    "continue_prompt": "Yes?",
    "date_ask_exact": "Which exact day would work for you?",
    "next_bd_offer": "That day is not a business day. Could you pay <amount> on <date> instead?",
    "deadline_offer": "The latest date I can record is <deadline>. Could you pay <amount> by then?",
    "past_date": "That date has already passed. Which day would work for you?",
    "floor_offer": "I understand. Could you pay <floor> by <date>?",
    "above_full_offer": "The amount due is <past_due>. Shall I record <past_due>?",
    "pay_on_date_question": "Would you like to pay on <date>?",
    "cannot_offer": "I'm afraid I can't offer that.",
    "account_error": "I'm sorry, I can't access the account details right now.",
    "hold": "One moment, please.",
    "anything_else": "Is there anything else I can help you with?",
}

# Generic code-level topics added to u_topic per stage (D.4). Not brief intents; handled in runtime code.
BUILTIN_TOPICS = {
    "rp": [
        {"id": "other_person", "description": "The speaker says they are not the person asked for.",
         "examples": ["No, this is his wife.", "I'm her son."], "negatives": ["Yes, speaking."]},
        {"id": "unavailable", "description": "The person asked for is not available right now.",
         "examples": ["He's at work.", "She's not home."], "negatives": ["That's me."]},
        {"id": "hold", "description": "The speaker will fetch the person asked for.",
         "examples": ["Hold on, I'll get him.", "One second, she's here."], "negatives": ["He's not here."]},
    ],
    "tp": [
        {"id": "unavailable", "description": "The person asked for is not available right now.",
         "examples": ["He's at work.", "She's away."], "negatives": ["Call back at three."]},
    ],
    "id": [
        {"id": "purpose_question", "description": "Asks what the call is about instead of answering the question.",
         "examples": ["What is this about?", "Why do you need that?"], "negatives": ["Are you a robot?"]},
    ],
    "neg": [],
    "conf": [],
}

# Partial Spec merged into missing keys only (deep merge; lists are not merged element-wise).
DEFAULTS = {
    "lines": DEFAULT_LINES,
    "interpretation": DEFAULT_INTERPRETATION,
    "banned": {"before_verification": [], "always": [], "never_offer": [], "never_ask": []},
    "right_party": {"max_asks": 2, "accept_own_name": True, "bare_no": "third_party",
                    "answers": {"who": "I am <self>.",
                                "why": "I can only explain that to <customer>.",
                                "other": "I'm sorry, I need to know who I am speaking with first."}},
    "third_party": {"disclose": "nothing_beyond_opening", "relative_may_verify": False, "relative_may_pay": False,
                    "turn_budget": 6,
                    "vague_line": "Could you tell me the exact day and time?",
                    "offer_to_pay_line": "Thank you, but I can only speak with <customer> about this."},
    "identity": {"one_at_a_time": True, "turn_budget": 12, "verified_prefix": "Thank you.", "hints": []},
    "products": {"floor_missing": "full", "unknown_type_spoken": "account"},
    "calendar": {"business_weekdays": [0, 1, 2, 3, 4], "holidays": [], "holiday_rules": [], "week_start": 0,
                 "count_from": "after_today", "numeric_order": "DMY",
                 "this_next": {"this": "current_week", "next": "following_week"}},
    "promise_date": {"earliest": {"kind": "today"}, "latest": {"kind": "deadline"}, "business_day_only": True,
                     "non_business_within_deadline": "offer_next_business_day", "after_deadline": "offer_deadline",
                     "offered_date_refused": "flat_refusal", "vague": {"ask_exact_times": 1, "then": "propose_deadline"},
                     "past_date": "say_passed_and_ask"},
    "amounts": {"never_ask_customer": True, "above_full": "offer_full", "decimals": 2},
    "negotiation": {"no_repeat_refused_offer": True, "non_answer_counts_as_refusal": True, "forbidden_offers": []},
    "notes": {"enabled": False, "scope": "product", "when": "no_promise_recorded", "reason_from": "product_situation",
              "skip_if_transfer": True, "text": ""},
    "multi_product": {"state_all_first": True, "ask_all_today_first": True, "order": "api",
                      "attempts_per_product": True, "one_date_for_all": "clamp_to_own_deadline_and_say",
                      "readback_together": True, "hardship_applies_to": "all_remaining",
                      "dispute_or_paid_continues": False,
                      "clamp_line": "For your <product>, the latest date I can record is <deadline>, so I will use that date."},
    "confirmation": {"verbatim_question": True, "on_change": "revalidate_then_readback",
                     "what_to_change": "What would you like to change?"},
    "recording": {"tries": 2},
    "closing": {"per_situation": {}},
    "required_sentences": [],
}


# Generic default wording per call language (language support, not brief content). Merged before DEFAULTS, so a
# Spec in that language never gets an English default line. Slots stand alone (no ending is attached to a slot).
DEFAULTS_BY_LANG = {
    "tr": {
        "lines": {
            "clarify": "Affedersiniz, tekrar söyler misiniz?",
            "no_info": "Üzgünüm, bu konuda bilgim yok.",
            "ack": "Anlıyorum.",
            "neutral_reask": "Bu sizin için uygun olur mu?",
            "continue_prompt": "Evet?",
            "date_ask_exact": "Hangi gün sizin için uygun olur?",
            "next_bd_offer": "O gün iş günü değil. Tarih: <date>, tutar: <amount>. Bu sizin için uygun olur mu?",
            "deadline_offer": "Kaydedebileceğim en geç tarih: <deadline>. Bu tarihe kadar <amount> ödeyebilir misiniz?",
            "past_date": "Bu tarih geçti. Hangi gün sizin için uygun olur?",
            "floor_offer": "Anlıyorum. Tarih: <date>, tutar: <floor>. Bu sizin için uygun olur mu?",
            "above_full_offer": "Ödenmesi gereken tutar: <past_due>. Bu tutarı kaydedeyim mi?",
            "pay_on_date_question": "Ödemeyi şu tarihte yapmak ister misiniz: <date>?",
            "cannot_offer": "Maalesef bunu sunamıyorum.",
            "account_error": "Üzgünüm, şu anda hesap bilgilerine ulaşamıyorum.",
            "hold": "Bir dakika lütfen.",
            "anything_else": "Size yardımcı olabileceğim başka bir konu var mı?",
            "amount_change_ask": "Hangi tutarı ödemek istersiniz?",
        },
        "right_party": {"answers": {"who": "Ben <self>.",
                                    "why": "Bunu yalnızca <customer> ile konuşabilirim.",
                                    "other": "Üzgünüm, önce kiminle konuştuğumu bilmem gerekiyor."}},
        "third_party": {"vague_line": "Tam gün ve saati söyleyebilir misiniz?",
                        "offer_to_pay_line": "Teşekkür ederim, ancak bu konuyu yalnızca <customer> ile konuşabilirim."},
        "identity": {"verified_prefix": "Teşekkür ederim."},
        "products": {"unknown_type_spoken": "hesap"},
        "multi_product": {"clamp_line": "Bu ürün için kaydedebileceğim en geç tarih: <deadline>. Bu tarihi kullanacağım."},
        "confirmation": {"what_to_change": "Neyi değiştirmek istersiniz?"},
    },
}


def _lang(spec):
    try:
        return str(((spec.get("bank") or {}).get("language")) or spec.get("language") or "en").strip().lower()[:2]
    except Exception:
        return "en"


def apply_defaults(spec):
    """Fill missing keys of `spec` from DEFAULTS (deep merge for dicts; a present list is never touched).

    Returns (new_spec, applied) where applied is a sorted list of JSON pointers that were filled,
    e.g. ["/interpretation/hedged_time", "/lines/hold"]. Must not mutate the input. [agent 5]

    A key whose value is None counts as missing. A present value of a different type is left alone (validation
    reports it). Pointers use RFC 6901 escaping.
    """
    import copy

    def esc(k):
        return str(k).replace("~", "~0").replace("/", "~1")

    applied = []

    def merge(dst, src, ptr):
        for k, dv in src.items():
            p = ptr + "/" + esc(k)
            if k not in dst or dst[k] is None:
                dst[k] = copy.deepcopy(dv)
                applied.append(p)
            elif isinstance(dst[k], dict) and isinstance(dv, dict):
                merge(dst[k], dv, p)

    out = copy.deepcopy(spec) if isinstance(spec, dict) else {}
    lang = _lang(out)
    if lang in DEFAULTS_BY_LANG:
        merge(out, DEFAULTS_BY_LANG[lang], "")
    merge(out, DEFAULTS, "")
    return out, sorted(applied)
