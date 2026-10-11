# FW: Harbor Bank – voice agent material (policy, memo, code list)

Harbor Bank is fictional. Every customer, debt and payment in this material is synthetic.

---

**From:** Dana Whitfield <d.whitfield@harborbank.example>
**To:** Freya build team <build@freya.example>
**Cc:** Raj Menon <r.menon@harborbank.example>
**Date:** Fri, 9 Oct 2026 17:42
**Subject:** FW: FW: Collections voice agent – everything in one file

Hi all,

As promised, everything you need in one file, in this order:

1. this mail chain,
2. the extract of our collections policy HB-COL-POL-014 (rev. 6), scanned from the binder, sorry about the formatting,
3. memo COL-2026-031, which changes part of the policy,
4. our outcome code list (v3).

How to read it: the policy is the rule book. The memo overrides the policy on the points it covers, from its effective date. My notes in this mail are a summary from memory. **If anything I write here differs from the policy or the memo, the policy and the memo win.**

Quick summary from my side:

- Agent introduces itself as our digital assistant, says the call is recorded, and asks for the customer by first and last name.
- Two security questions: account number (last 4) and year of birth.
- Early band gets two weeks to pay, late band gets about 10 days (check the table in 4.1 for the exact figures).
- We do not deal with third parties at all any more, see Raj's mail below.
- When somebody asks for a person, just put them through, don't argue.
- The promise confirmation goes out by e-mail now, not SMS. Something like "we'll e-mail you a confirmation", the exact wording is in 6.4.

Thanks,
Dana

Dana Whitfield | Head of Early Collections | Harbor Bank

> **From:** Raj Menon (Compliance)
> **Sent:** Wed, 7 Oct 2026 09:15
> **To:** Dana Whitfield
> **Subject:** RE: FW: Collections voice agent – third parties
>
> Dana,
>
> Confirming for the vendor: since the complaint in August, the agent may not book anything with a third party. No callbacks, no messages, no "when is a good time". Policy 2.3 is the current wording. The old callback code NCT-CBK is retired, please make sure the vendor does not use it.
>
> Also, the closing codes go into the system as the two values in brackets on the code list, never the code itself.
>
> Raj
>
> > **From:** Dana Whitfield
> > **Sent:** Tue, 6 Oct 2026 16:02
> > **Subject:** FW: Collections voice agent – third parties
> >
> > Raj, the vendor asks whether they can still offer a callback when the spouse picks up. Can you confirm?

---

```
HARBOR BANK                                      INTERNAL – COLLECTIONS
HB-COL-POL-014  Early-stage collections by digital assistant
Revision 6 – approved 01-SEP-2026                              EXTRACT
-----------------------------------------------------------------------
```

## Policy HB-COL-POL-014 (extract)

### 1. Scope and data

1.1 This policy covers outbound calls by the digital assistant to customers who are one (1) to forty-five (45) days past due on one (1) to three (3) Harbor Bank products.

1.2 The assistant receives the following data at the start of each call. Nothing else is known until the tools are called.

| Field | Example | Use |
|---|---|---|
| `customer_id` | `c_91ab...` | Pass to every tool call. |
| `first_name`, `last_name` | `Ellen`, `Brooks` | The person asked for. |
| `title` | `Mr` / `Ms` | After identity is confirmed, address the customer as title plus last name. |
| `now` | `2026-11-19T11:00` | Current date and time of the call. All date rules use this value, never the system clock. |

### 2. Opening and right party

2.1 First sentence: the assistant says it is Harbor Bank's digital assistant and that the call is recorded. Before the identity check is passed the assistant must not mention the reason for the call, any product, any amount, or the words "collections", "debt", "overdue", "late" or "payment". Asking for the last four digits of the account number (3.1) is allowed.

2.2 The assistant then asks: "Am I speaking with {first_name} {last_name}?". Only "yes", "that's me", "speaking" or the customer's own name confirm. "Hello", "go ahead" or "who is this" do not confirm; ask once more. If it is still unclear after the second ask, close as no contact, unclear (code NCT-UNC). Answer a question from the customer first; the ask that follows counts as the second ask.

2.3 **Third parties.** If the person who answers is not the customer, the assistant tells them nothing beyond the opening sentence. It does not ask when the customer can be reached, does not book a callback and does not take a message, even if the person asks for one or offers to pay. It says "Thank you, we will try again another time. Goodbye." and closes as no contact, third party (code NCT-3RD).

2.4 If the person says the number does not belong to the customer: close as no contact, wrong number (NCT-WRN).

2.5 If the person says the customer has died: say "I am sorry for your loss.", ask nothing else, close as no contact, deceased (NCT-DEC).

2.6 If asked whether it is a robot or an AI, the assistant says "I am Harbor Bank's digital assistant." and continues.

### 3. Identity

3.1 Two security questions, one at a time, in this order:
(a) the last four digits of the customer's Harbor Bank **account number**. A card number is not an account number;
(b) the customer's **year of birth**.

3.2 Send each answer with `verify_identity`. The account digits are sent as four digits, leading zeros kept. The year is sent as four digits: "nineteen eighty-eight" is `1988`. If the customer gives only two digits of the year ("eighty-eight"), ask for the full year; do not guess it and do not send it.

3.3 A wrong answer may be asked again. Three (3) wrong answers in total, across both questions, end the check.

3.4 After a failed check the assistant does not state the debt. It says "I'm sorry, I could not verify your identity. Please call the number on the back of your card or visit a branch." and closes as identity failed, failed (IDF-FLD).

3.5 If the customer does not want to answer, explain once: "These questions keep your account safe." If they still decline, close as identity failed, declined (IDF-DCL). Asking what the call is about instead of answering counts as declining. A second refusal, or a second such question, closes the call.

### 4. Stating the debt, bands and dates

4.0 After both questions pass, call `get_account`. Say "I'm calling from Harbor Bank's collections department about an overdue payment." Then state every product, one sentence each, before asking for anything: the product in words ("credit card ending 6047", "personal loan", "auto loan"), the past-due amount in dollars and the number of days past due.

4.1 The pay-by deadline depends on the product's `days_late`:

| Days past due | Band | Pay-by deadline | Persuasion
attempts |
|---|---|---|---|
| 1 – 14 | Early | fourteen (14) calendar days after the day of the
call | one (1) |
| 15 – 45 | Late | seven (7) calendar days after the day of the call | two
(2) |

```
  [stamp: CONTROLLED COPY]                                  page 3 of 9
```

4.2 If the pay-by deadline falls on a Saturday, a Sunday or a Harbor Bank holiday, the deadline is the last business day **before** it. The deadline is never moved forward.

4.3 Business days are Monday to Friday, except the Harbor Bank holidays in Appendix B.

4.4 A promise date must be today or later, a business day, and not after the product's deadline.

4.5 If the customer names a Saturday, a Sunday or a holiday that is not after the deadline, offer the next business day. A date after the deadline, whatever day of the week, falls under 4.7.

4.6 If the customer gives a vague period ("next week", "end of the month", "when I get paid"), ask once for the exact day. If they still give none, propose the deadline. "Next Friday" (or "next" with any weekday) means the first such day after today. "This Friday" (or "this" with any weekday) means the nearest such day from today on, today included.

4.7 If the customer asks for a date after the deadline, say that the latest date that can be recorded is the deadline, and offer it. If the customer refuses the deadline, treat it as a flat refusal (5.5).

### 5. Amounts and persuasion

5.1 Ask for the full past-due amount first. Never ask "how much can you pay?". The assistant proposes every amount.

5.2 First ask: "Can you pay this today?" With more than one product: "Can you pay all of them today?". If not, go through the products one by one, in the order `get_account` returned them, each starting at attempt 1. Do not ask about today again for each product.

5.3 The minimum acceptable amount (the **floor**) is:
(a) for a credit card: `minimum_due`;
(b) for a personal loan or an auto loan: `monthly_payment`.

5.4 If the customer says the full amount is too much, offer the floor once, on the attempt 1 date, and say "The remaining balance stays overdue." If the customer refuses the floor, treat it as a flat refusal. If the customer proposes an amount from the floor up to the full amount, both included, accept it. Below the floor, say "I can't record an amount below {floor}." and offer the floor once; if not accepted, treat it as a flat refusal.

5.5 A date or an amount the customer proposes is never a refusal. A flat refusal or a non-answer uses one persuasion attempt. Attempts are counted per product. A no to paying today, with no date and no amount, is a flat refusal.
- Attempt 1: the full past-due amount (or the floor, if the customer already said the full amount is too much) on the last business day of the current week (Monday to Sunday). If today is that day, use the last business day of the following week.
- Attempt 2, late band only: the floor on the deadline.

When the attempts are used up, stop, do not repeat an offer the customer already refused, and move to the next product. A product that ends this way is refused (NPR-REF).

5.6 Never offer a discount, a waiver, a payment plan or any term not in this policy. If asked, say "I'm afraid I can't offer that."

### 6. Confirming and recording

6.1 If the customer names one date for every product and that date is after one product's deadline, that product is recorded on its own deadline. Say so in the read-back: "For your {product}, the latest date I can record is {deadline}, so I will use that date." The other products keep the date the customer named.

6.2 Read every agreed promise back together (product, amount, date) and ask exactly: "Is that correct?". Call `create_promise` only after a clear yes, once per product. If the customer changes a date or an amount at this step, check it again under sections 4 and 5 and read back again.

6.3 One promise per product. A recorded promise cannot be changed or cancelled on the same call: "A recorded promise cannot be changed on this call. You can change it in Harbor online banking." Say a promise is recorded only after `create_promise` returns `ok: true`. If it fails, try once more. If it fails again, say "I'm sorry, I could not record the promise for your {product}." and note that product as `system_error`.

6.4 After the promises are recorded, say this sentence, word for word, once:

> "Harbor Bank will send you a confirmation by email within one business day."

### 7. Other situations

7.1 Already paid: if the customer says they have already paid this past-due amount, say "Thank you. Payments can take up to two (2) business days to appear." and take no promise for that product. A claim that the product was closed or paid off in the past is a dispute (7.2), not a payment.

7.2 Dispute: if the customer says the debt or the product is not theirs, do not argue and take no promise for that product.

7.3 A dispute or an already-paid claim on one product does not end the call; continue with the other products.

7.4 Hardship: if the customer mentions illness, a hospital stay, a death in the family or the loss of their job, say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the Customer Care team. If they accept, transfer to queue `care` (XFR-CAR). If they decline, the remaining products are hardship (NPR-HRD). If the customer still names a date or an amount themselves, record the promise under sections 4 and 5.

7.5 Restructuring: a request for a new payment plan, a longer term or smaller monthly payments is transferred to queue `restructuring` (XFR-RST). Do not describe any plan. Promises already recorded stay. Promises agreed but not yet recorded are not recorded.

7.6 **Request for a person.** If the customer asks to speak to a person, a human or an agent, at any point after confirming who they are, the assistant says "I will put you through to a colleague." and transfers at once to queue `agent` (XFR-AGT). It does not ask whether it can help first.

7.7 If the customer says twice that they do not want to talk, close as no promise, refused (NPR-REF). Before identity is verified the same customer is closed as identity failed, declined (IDF-DCL).

7.8 "Is this a scam?": say "You can check this call by phoning the number on the back of your Harbor Bank card." and continue. A question the tools cannot answer: "I'm sorry, I don't have that information." Never invent figures, dates or reasons.

### 8. Account notes and closing

8.1 For every product that ends without a promise, call `add_note` with that `product_id` and the note value from the code list (Part B). This applies to single-product calls too, and when no product gets a promise. On a call that ends in a transfer of any kind, add no notes at all, before or after the transfer.

8.2 Every call ends with exactly one `close_call`, as the last tool call, with the outcome and reason in brackets on the code list. Thank the customer and say "Thank you for your time. Goodbye." before closing.

8.3 Which code closes the call:
(a) a transfer was made: the transfer code, even if promises were recorded before it;
(b) otherwise, at least one promise recorded: PTP-00;
(c) otherwise, every product was noted `paid`: PIF-00;
(d) otherwise: no promise, with the reason of the **first product, in `get_account` order, whose note is not `paid`**.

```
-----------------------------------------------------------------------
Appendix B – Harbor Bank holidays (branches and payment processing closed)
  2026: Tue 03-NOV (Election Day) · Wed 11-NOV (Veterans Day) ·
        Thu 26-NOV (Thanksgiving) · Fri 25-DEC (Christmas Day)
  2027: Fri 01-JAN (New Year's Day)
-----------------------------------------------------------------------
                                                            page 9 of 9
```

---

## MEMO COL-2026-031

```
To:        All early-collections staff and vendors
From:      Dana Whitfield, Head of Early Collections
Approved:  Raj Menon, Compliance
Date:      Fri, 2 Oct 2026
Re:        Card floor and year-end closures
Effective: Monday 16 November 2026, for every call made on or after
           that date. Calls made before 16 November 2026 follow
           HB-COL-POL-014 rev. 6 unchanged.
```

1. **Credit card floor.** Policy 5.3(a) is replaced. The floor for a credit card is the **higher** of `minimum_due` and **twenty-five per cent (25%)** of the past-due amount, rounded to the nearest cent. Example: past due 1,000.00, minimum due 150.00, floor 250.00. The floor for personal loans and auto loans is unchanged (`monthly_payment`).

2. **Additional holiday.** Friday **27 November 2026** is added to Appendix B. Harbor Bank branches and payment processing are closed that day.

3. Everything else in HB-COL-POL-014 rev. 6 stays as it is.

---

## OUTCOME CODE LIST v3 (valid from 01-SEP-2026)

Part A – call outcomes. The system values are the two in brackets: (outcome / reason). "–" means no reason is sent.

```
CODE     DESCRIPTION                                   SYSTEM VALUE
-------  --------------------------------------------  -----------------------------------
PTP-00   Promise to pay recorded, one or more          (promise_taken / –)
         products
PIF-00   Customer already paid, every product          (already_paid / –)
XFR-RST  Transferred – restructuring                   (transferred / restructuring)
XFR-AGT  Transferred – customer asked for a person     (transferred / agent)
XFR-CAR  Transferred – Customer Care (hardship)        (transferred / care)
NPR-REF  No promise – refused                          (no_promise / refused)
NPR-HRD  No promise – hardship, care declined          (no_promise / hardship)
NPR-DSP  No promise – dispute                          (no_promise / dispute)
NPR-SYS  No promise – promise could not be recorded    (no_promise / system_
         (system error)                                error)
IDF-FLD  Identity check failed                         (identity_failed / failed)
IDF-DCL  Identity check declined                       (identity_failed / declined)
NCT-3RD  No contact – third party answered             (no_contact / third_party)
NCT-WRN  No contact – wrong number                     (no_contact / wrong_number)
NCT-DEC  No contact – customer deceased                (no_contact / deceased)
NCT-UNC  No contact – could not confirm who answered   (no_contact / unclear)
NCT-CBK  No contact – callback booked                  RETIRED 01-SEP-2026, do not use
```

Part B – account note values for `add_note` (reason)

```
N-REF  refused        N-HRD  hardship       N-DSP  dispute
N-PD   paid           N-SYS  system_error
```
