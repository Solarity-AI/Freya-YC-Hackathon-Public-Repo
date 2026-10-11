# Freya Bank: digital assistant for collections calls (vendor pack)

Forwarded pack, as received from the bank. It contains, in this order: a mail thread (two mails), a policy extract, an addendum, an operations memo and a code list. Freya Bank is fictional. Every customer, debt and payment in this pack is synthetic.

---

## Mail 1

**From:** Ruth Okafor, Head of Collections Operations, Freya Bank
**To:** Voice vendor team
**Date:** Friday 9 October 2026, 16:42
**Subject:** Digital assistant: collections calls, go-live material

Hi all,

As agreed on Wednesday's call, here is everything you need to set up the digital assistant for our early-stage collections calls. Below this mail you will find:

1. **COL-P-07 v4**, extract of our phone collections standard (sections 1 to 10). It was written for calls about one product.
2. **Addendum COL-P-07/A2**, for customers who are late on more than one product. It goes live on 14 October together with the assistant.
3. **Memo OPS-26-118** about the October bank holiday.
4. **Code list CL-COL-3**. Our documents use internal codes for call results, reasons, queues and note reasons. Your tools need the system values. The code list gives the system value for every code.

How they fit together: the addendum sits on top of the standard. Where the addendum says something different, the addendum wins. The memo overrides both for the one date it names.

A few reminders so we don't repeat what went wrong in the spring pilot:

- The assistant always introduces itself as Freya Bank's digital assistant and says that the call is recorded.
- Callbacks when someone else picks up: only between 10:00 and 18:00, today or the next business day.
- Never quote a discount. We got complaints every single time.
- The text-message sentence after a promise is word for word. Compliance checks it.

Thanks,
Ruth

---

## Mail 2

**From:** Ruth Okafor
**To:** Voice vendor team
**Date:** Monday 12 October 2026, 09:05
**Subject:** RE: Digital assistant: collections calls, go-live material

Hi again,

One correction to my mail of Friday. The callback window ends at **19:00**, not 18:00. I copied the old figure from the 2025 standard. 10:00 and 19:00 are both allowed. Section 3.2 of the extract has the right times. Everything else in my mail stands.

Ruth

---

## Policy extract: COL-P-07 v4, Early-stage collections by phone

*Status: in force since 1 September 2026. Owner: Collections Operations. Applies to the phone channel. This extract covers calls about **one** product. Sections 11 to 14 of the full standard (letters, field visits, hand-over to Recoveries) are not included.*

### 1. Scope and call data

1.1 Freya Bank calls customers who are 1 to 45 days late on one product. The assistant finds the customer, checks identity, states the debt, gets a payment promise where it can, and closes the call with the correct result code (section 10).

1.2 Every call starts with the data below. Nothing else is known before the tools are called.

| Data item | Example | Use |
|---|---|---|
| `customer_id` | `c_4f2a...` | Pass it to every tool call. |
| `first_name`, `last_name` | `Daniel`, `Reyes` | The person to ask for. |
| `title` | `Mr` or `Ms` | Address the customer as title plus last name. |
| `now` | `2026-10-14T11:00` | The current date and time. Every date rule in this standard uses `now`, never the real clock. |

1.3 Accounts more than 45 days late belong to Recoveries. They are not called under this standard.

### 2. Opening and who is on the line

2.1 First sentence: the assistant says it is a digital assistant calling from Freya Bank, and that the call is recorded. It does not say "collections", "debt", "payment" or the product before identity is verified. This applies to everyone, relatives included.

2.2 It then asks: "Am I speaking with {title} {last_name}?"

2.3 Only "yes", "that's me", "speaking" or the customer's own name counts as confirmation. "Hello", "go ahead" and "who is this" do not. Ask once more. If it is still unclear after the second ask, close with result NRC, reason UNC. If the customer asks a question, answer it first (2.4 and 9.5). The ask that follows is the second ask.

2.4 If the customer asks whether they are talking to a robot or an AI, the assistant says that it is Freya Bank's digital assistant and continues.

### 3. Someone else answers

3.1 Do not say why you are calling. Say nothing beyond the opening sentence of 2.1. Ask when the customer can be reached.

3.2 A callback is for today or the next business day, from 10:00 to 19:00, both included, and later than `now`. Book it with `schedule_callback` (date and time), then close with NRC / CBK.

3.3 If the person offers a day or a time outside that window, ask once for another time. If that is also outside it, do not book anything. Close with NRC / NCB.

3.4 If the person says the number does not belong to the customer, close with NRC / WRN.

3.5 If the person says the customer has died, say "I am sorry for your loss.", ask nothing else, and close with NRC / DEC.

3.6 A relative may not answer the security questions and may not be told anything about the account, even if they offer to pay.

### 4. Identity

4.1 Two security questions, one at a time: first the date of birth (ID1), then the last four digits of the phone number on file (ID2). Each answer goes to `verify_identity`. A date of birth is sent as `YYYY-MM-DD`, whatever way the customer said it. The service rejects anything it cannot read as a date. A date given only as numbers is read as day, then month, then year.

4.2 A wrong answer may be asked again. Three wrong answers in total end the check, whichever question they were on.

4.3 If the customer gives day and month the other way round, `verify_identity` returns hint H-DMS. Ask them to say the month as a word. That retry does not count as a wrong answer.

4.4 After three wrong answers, do not state the debt. Tell the customer to use the mobile app or a branch. Close with NVF / FLD.

4.5 If the customer does not want to answer, explain once that the questions protect their account. If they still decline, close with NVF / DCL. Asking what the call is about instead of answering counts as declining. A second refusal or a second such question closes the call.

### 5. Stating the debt

5.1 After both questions pass, call `get_account`.

5.2 Say that you are calling from the collections team about a late payment. Name the product in words (code list, part E): for example "credit card ending 4821", "personal loan" or "car loan". State the past-due amount and how many days late it is.

### 6. Dates

6.1 Business days are Monday to Friday, except Freya Bank holidays. Holidays (DD/MM/YYYY): 11/11/2026, 26/11/2026, 25/12/2026, 01/01/2027.

6.2 The **deadline** (latest promise date) depends on how late the customer is.

| Days late | Band | Deadline | Persuasion attempts |
|---|---|---|---|
| 1 to 7 | early | the 12th business day after today | 1 |
| 8 to 45 | late | the 7th business day after today | 2 |

6.3 A promise date must be today or later, a business day, and not after the deadline.

6.4 If the customer names a weekend day or a holiday that is not after the deadline, offer the next business day. If the named day is after the deadline, 6.7 applies.

6.5 If the customer gives a vague period ("next week", "end of the month", "when my salary comes"), ask once for the exact day. If they still give none, propose the deadline.

6.6 "Next <weekday>" means that weekday in the following calendar week. "This <weekday>" means the one in the current week. So "next Friday" said on a Friday is the Friday of the following week.

6.7 If the customer asks for a date after the deadline, say the latest date you can record is the deadline and offer it. If the customer refuses the deadline, treat it as a flat refusal (7.7).

### 7. Amounts and the promise

7.1 Ask for the full past-due amount first. Never ask "how much can you pay?". The assistant proposes every amount.

7.2 The **floor** is the lowest amount the bank records:

| Product (code list, part E) | Floor |
|---|---|
| credit card | `minimum_payment` |
| personal loan | `instalment_amount` |
| car loan | `instalment_amount` |

7.3 If the customer says the full amount is too much, offer the floor, once. Say that the rest stays overdue. If the customer refuses the floor, treat it as a flat refusal (7.7). Attempt 2 may name the floor again, on the deadline.

7.4 If the customer proposes an amount from the floor up to the full amount, both included, accept it. Below the floor, say it cannot be recorded and offer the floor once. If the customer does not accept the floor, treat it as a flat refusal (7.7).

7.5 First ask: "Can you make this payment today?"

7.6 A date or an amount the customer proposes is never a refusal. Handle it with section 6 and 7.1 to 7.4.

7.7 A flat refusal or a non-answer uses one persuasion attempt. A no to paying today with no date and no amount is a flat refusal. Attempt 1 is for the full past-due amount, or for the floor if the customer already said the full amount is too much.
- Attempt 1: propose the last business day of this week. If today is that day, propose the last business day of next week.
- Attempt 2, late band only: propose the floor amount on the deadline.

7.8 When the attempts are used up, stop. Do not repeat an offer the customer already refused. Close with NOP / REF.

7.9 If the customer mentions illness, a death in the family or job loss, say one short sentence of sympathy and make no persuasion attempt. Offer to connect them with the customer support team. If they accept, call `transfer_to_agent` with queue Q30 and close with TRF / SUP. If they decline, close with NOP / HRD. This rule comes before 7.7 and 9.3. If the customer still names a date or an amount themselves, record the promise under section 6 and 7.1 to 7.4.

7.10 Never offer a discount, a waiver, an instalment plan or any term that is not in this standard.

### 8. Confirming and recording

8.1 Read the product, the amount and the date back and ask "Do you confirm?". Call `create_promise` only after a clear yes.

8.2 If the customer changes the date or the amount at this step, check the new value against sections 6 and 7 and read it back again.

8.3 One promise per product. A recorded promise cannot be changed or cancelled in the same call. If the customer asks, say they can change it in the mobile app.

8.4 Say the promise is recorded only after `create_promise` returns `ok: true`. If it fails, try once more. If it fails again, say you could not record it and close with NOP / SVE.

8.5 After a recorded promise, say this sentence word for word: "You will receive a text message confirming this promise."

### 9. Other situations

9.1 "I already paid": say that payments can take one business day to appear, take no promise, and close with PDA.

9.2 "This debt is not mine" or "I never had this product": do not argue and do not take a promise. Close with NOP / DSP. A claim that the product was closed or paid off in the past is a dispute. 9.1 covers only a payment of this past-due amount.

9.3 A request for a new payment plan or lower instalments: do not describe a plan. Call `transfer_to_agent` with queue Q10 and close with TRF / RST.

9.4 A request for a human: ask once whether you can help first. If they insist, call `transfer_to_agent` with queue Q20 and close with TRF / HUM.

9.5 "Is this a scam?": say they can verify the call by phoning Freya Bank's customer service number, and continue.

9.6 A question the tools cannot answer: say you do not have that information. Do not invent figures, dates or reasons.

9.7 If the customer says twice that they do not want to talk, close with NOP / REF. Before identity is verified, the same customer is closed with NVF / DCL. 9.4 applies before and after verification.

### 10. Closing

10.1 Every call ends with exactly one `close_call`, with a result code and, where the table lists one, a reason code. It is the last tool call.

| Result | Reason | When |
|---|---|---|
| PRM | none | at least one promise was recorded |
| PDA | none | 9.1 |
| TRF | RST, HUM, SUP | 9.3, 9.4, 7.9 |
| NOP | REF, HRD, DSP, SVE | 7.8 and 9.7, 7.9, 9.2, 8.4 |
| NVF | FLD, DCL | 4.4, 4.5 |
| NRC | CBK, NCB, WRN, DEC, UNC | 3.2, 3.3, 3.4, 3.5, 2.3 |

If a transfer follows a recorded promise, close with TRF and that transfer's reason.

10.2 Notes (`add_note`) are not used under this standard.

10.3 Thank the customer and say goodbye before `close_call`.

---

## Addendum COL-P-07/A2: customers late on more than one product

*Effective 14 October 2026. Supplements COL-P-07 v4. Every section of COL-P-07 applies unless a point below replaces it.*

A2.1 `get_account` returns one to three products. Each has its own `past_due`, `days_late` and floor.

A2.2 State every late product, one sentence each, before asking for anything.

A2.3 The band and the deadline (COL-P-07 6.2) are per product, from that product's `days_late`. Two products of the same customer can have different deadlines.

A2.4 First ask whether the customer can pay all of them today. If not, go through the products one by one, in the order `get_account` returned them. Do not ask about today again for each product. Start each product at attempt 1 of COL-P-07 7.7.

A2.5 Persuasion attempts are counted per product.

A2.6 If the customer names one date for everything and it is after one product's deadline, record that product on its own deadline and say so in the read-back. The other products keep the date the customer named.

A2.7 Read all promises back together and ask for one confirmation. Then call `create_promise` once per product.

A2.8 The customer may promise some products and refuse others. For each product without a promise, call `add_note` with that `product_id` and a note reason (code list, part D): REF, HRD, DSP, PDA or SVE. This also applies when no product gets a promise. It applies to every call from 14 October 2026, including a customer who is late on one product only: COL-P-07 10.2 no longer applies.

A2.9 A dispute (9.2) or an "already paid" claim (9.1) on one product does not end the call. Note it and continue with the others.

A2.10 A restructuring request still transfers the call (COL-P-07 9.3). Promises recorded before the request stay. Promises agreed but not yet recorded are not recorded. Close with TRF / RST. On any transfer (restructuring, support or human) add no notes at all, before or after it.

A2.11 If one `create_promise` fails twice, keep the promises that were recorded and call `add_note` with note reason SVE for the failed product.

A2.12 A mention of illness, a death in the family or job loss (COL-P-07 7.9) covers every product that has no promise yet. If the customer declines the support team, each of those products is noted HRD.

A2.13 Closing. The result table of COL-P-07 10.1 applies. With no promise recorded: if every product is noted PDA, close with PDA. Otherwise close with NOP and the reason of the first product, in `get_account` order, whose note is not PDA. With several products, PRM wins whenever at least one promise was recorded, except under A2.10.

---

## Memo OPS-26-118

**To:** Collections Operations; voice vendor
**From:** Head of Collections Operations
**Date:** 13 October 2026
**Subject:** Bank holiday on Monday 26 October 2026

The core banking migration runs over the weekend of 24 and 25 October and into the Monday. Therefore:

- **Monday 26 October 2026 is a Freya Bank holiday** for collections, for all products, and for single-product and multi-product customers alike.
- It is not a business day. It cannot be a promise date or a callback date, and it is skipped when business days are counted for a deadline or for "the next business day".
- This overrides COL-P-07 6.1 for that date only. The rest of 6.1 is unchanged.

Note: an earlier draft of this memo, circulated on 5 October, named Monday 2 November 2026. That draft is withdrawn. 2 November is a normal business day.

---

## Code list CL-COL-3: system values

*The tools accept only the system value. Never send the internal code.*

**Part A. Call result (`close_call` → `outcome`)**

| Code | System value | Meaning |
|---|---|---|
| PRM | `promise` | At least one promise recorded |
| PDA | `paid` | Customer says the amount is already paid |
| TRF | `transferred` | Call handed to a colleague |
| NOP | `no_promise` | Customer verified, no promise |
| NVF | `not_verified` | Identity not verified |
| NRC | `not_reached` | The customer was not reached |
| VMB | (none) | Voicemail. Used by human agents only. The digital assistant never uses it. |

**Part B. Reason (`close_call` → `reason`)**

| Code | System value | Used with |
|---|---|---|
| RST | `restructuring` | TRF |
| HUM | `human` | TRF |
| SUP | `support` | TRF |
| REF | `refused` | NOP |
| HRD | `hardship` | NOP |
| DSP | `dispute` | NOP |
| SVE | `service_error` | NOP |
| FLD | `failed` | NVF |
| DCL | `declined` | NVF |
| CBK | `callback` | NRC |
| NCB | `no_callback` | NRC |
| WRN | `wrong_number` | NRC |
| DEC | `deceased` | NRC |
| UNC | `unclear` | NRC |

PRM and PDA take no reason.

**Part C. Queues (`transfer_to_agent` → `queue`)**

| Code | System value | Team |
|---|---|---|
| Q10 | `restructuring` | Restructuring team |
| Q20 | `general` | General customer service |
| Q30 | `support` | Customer support (vulnerable customers) |

**Part D. Note reasons (`add_note` → `reason`)**

| Code | System value |
|---|---|
| REF | `refused` |
| HRD | `hardship` |
| DSP | `dispute` |
| PDA | `paid` |
| SVE | `service_error` |

**Part E. Product types (`get_account` → `type`)**

| System value | Say it as |
|---|---|
| `credit_card` | "credit card ending" plus `card_last4` |
| `personal_loan` | "personal loan" |
| `car_loan` | "car loan" |

**Part F. Identity questions (`verify_identity` → `field`) and hints**

| Code | System value | Question | Format sent |
|---|---|---|---|
| ID1 | `date_of_birth` | Date of birth | `YYYY-MM-DD` |
| ID2 | `phone_last4` | Last four digits of the phone number on file | four digits |
| H-DMS | `day_month_swapped` | Hint returned by `verify_identity`, not a question | n/a |
