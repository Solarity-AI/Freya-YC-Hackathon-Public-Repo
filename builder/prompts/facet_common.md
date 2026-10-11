# Task

Extract the facet @@FACET@@ of the Spec: the top-level keys @@KEYS@@.
Other facets are extracted in parallel by other calls from the same brief, so use the shared conventions below
exactly (especially the situation ids) so the pieces fit together.

# Output object

- "values": an object with the facet's top-level keys (@@KEYS@@), shaped by the schema.
- "sources": a list of {"pointer", "quote"}. "pointer" is a JSON pointer into "values" (e.g. "/bands/0",
  "/identity/questions/1/ask"); "quote" is the verbatim span of the brief that justifies it. Give at least one
  source for every key you set from the brief, and one for every table row, number, date, time, code and
  verbatim sentence. A pointer to a parent ("/bands") covers its children.
- "decisions": short strings, one per interpretation or default choice you made (what and why).
- "residual": rules of the brief that this facet should hold but the schema cannot express, as
  {"text": "<the rule, quoted or tightly paraphrased>", "class": "speech" | "flow"}. Empty list if none.
- "dated": rules of this facet that change on an effective date, as {"from": "YYYY-MM-DD" (first day the new rule
  applies), "until": "" (or the YYYY-MM-DD it stops applying), "pointer": a JSON pointer into "values" (the
  narrowest leaf that changes, e.g. "/bands/0/deadline/n", "/products/types/<type>/floor", "/calendar/holidays",
  "/third_party/callback/windows/0/to"), "value_json": the new value at that pointer as JSON text (e.g. "10",
  "{\"kind\": \"max\", \"args\": [...]}", the full new holidays list), "quote"}. Empty list if none.

# Shared conventions

Placeholders in spoken lines (closed set; anything else is an error):
- <bank> bank name, <self> how the agent names itself, <customer> how the customer is addressed,
  <v:VAR> a declared call variable (e.g. <v:surname>), <f:LEAF> a leaf of the current product from the account tool
  (e.g. <f:last4_leaf>), <product> the product's spoken form, <amount> <floor> <past_due> <rest> money,
  <date> <deadline> spoken dates, <days_late> an integer, <time> HH:MM, <items> the joined read-back items.
- A brief that writes a variable as {name} or `{name}` means <v:name>.
- Call language: write every spoken line in the call language of the brief (bank.language; the language its
  example conversations are in when it does not say), whatever language the rest of the brief uses. Copy a sentence
  the brief dictates word for word exactly. Use the example conversations for natural wording and the form of
  address. Placeholders stay as they are and are rendered in the call language by code (Turkish money
  "1.250,50 TL", dates "23 Ekim Cuma"). In a language with endings (Turkish) a placeholder always stands alone:
  "Tutar: <amount>.", "<date> tarihinde", "<product> için"; never "<amount>'ı", "<date>'de", "<product>ınız".
  Keep the grammar right around a slot: a definite object takes its case ending on a noun next to the slot, not on
  the slot ("<amount> tutarındaki ödemeyi <date> tarihinde yapabilir misiniz?", not "<amount> tutarı ... ödeyebilir").

Situation ids (shared by all facets). Use these ids for these meanings; use S_CUSTOM_1..S_CUSTOM_9 only for an
outcome the brief defines that none of these fit:
- S_PROMISE: at least one promise recorded.
- S_PAID: the customer already paid the past-due amount.
- S_DISPUTE: the customer denies the debt or the product.
- S_HARDSHIP_DECLINED: hardship, the customer declined the offered transfer.
- S_HARDSHIP_TRANSFER: hardship, the customer accepted the transfer.
- S_RESTRUCTURE_TRANSFER: asks for a new plan / lower instalments -> transfer.
- S_HUMAN_TRANSFER: insists on a human -> transfer.
- S_REFUSED_EXHAUSTED: persuasion attempts used up without a promise.
- S_REFUSED_TO_TALK: a verified customer refuses to talk.
- S_SERVICE_ERROR: a tool kept failing (e.g. the promise could not be recorded).
- S_ID_FAILED: identity check failed (too many wrong answers).
- S_ID_DECLINED: the customer declined the identity questions (or refused to talk before verification).
- S_CALLBACK: a third party gave a valid callback slot and it was booked.
- S_NO_CALLBACK: no valid callback slot.
- S_WRONG_NUMBER: the number does not belong to the customer.
- S_DECEASED: the customer has died.
- S_UNCLEAR: it never became clear who is on the line.

Rules (DateRule) and amounts (AmountRule) are evaluated by code at call time from the call's own "now":
- DateRule kinds: today | next_business_day | nth_business_day_after_today (n) | nth_calendar_day_after_today (n,
  roll none|next_bd|prev_bd) | last_business_day_of_week (if_today keep|next_week) | end_of_month (roll) |
  last_business_day_of_month | deadline (the product's band deadline) | fixed (date) | min/max (args).
  "The 5th business day after today" = {"kind": "nth_business_day_after_today", "n": 5}.
- AmountRule kinds: full (the past-due amount) | floor (the product type's floor) | field (a product leaf) |
  percent_of_full (pct, rounding) | fixed (value) | min/max (args) | floor_if_too_much_else_full.
- Money is never asked from the customer unless the brief says so; the agent proposes amounts.

Several documents (raw material). The brief may be a stack: e-mails, a policy extract, memos, a code list, or
several files given as layers (a later LAYER amends an earlier one; DOCUMENTs from a folder have no order, use the
rules below). Then:
- Instructions in a mail or memo are rules; background, history ("last year we allowed ...") and opinions are not.
- A later amendment replaces the rule it amends. Explicit replacement ("supersedes", "is replaced by",
  "no longer applies", "is withdrawn") wins; then the later effective date; then the later document date; then
  memo > policy extract > mail. A draft, proposal or "for consultation" document is background only.
- An amendment with an effective date is evaluated by code on each call's own date, so never pick one version from
  the example dates: "values" hold the rule as it was before the amendment (the policy as written, plus amendments
  without a date), and every dated amendment becomes a "dated" entry, whether its date is before or after the
  brief's example dates. Several changes from one amendment are several entries with the same "from". Relative
  effective dates ("from next Monday") count from the amendment's own date. A spoken line that states a dated value
  (e.g. a callback window in reach_reask) gets its own dated entry. Only these sections can be dated: bands,
  calendar, third_party, promise_date, amounts, negotiation, products (types, max), statement, confirmation,
  closing, lines, multi_product, recording, notes. Use a residual rule for a dated change anywhere else (identity,
  intents, situations, outcomes) or one that is not a value at a pointer of this facet; record the choice in
  "decisions".
- A code list maps meanings to codes. Wire values are the codes the API expects: if the API field has an enum, the
  value must be one of its members; if it has no enum, use the brief's code exactly as written (keep leading
  zeros). Never send a prose label where a code is expected.
- Holidays given as named days or rules ("first Monday of May", "25 December, moved to Monday if on a weekend") go
  to calendar.holiday_rules; dated holidays go to calendar.holidays as YYYY-MM-DD.

# Generic defaults (filled by code for keys you omit)

@@DEFAULTS@@

# Facet instructions

@@FACET_TEXT@@
@@FEEDBACK@@