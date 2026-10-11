# Freya Bank: material for the early-collections voice assistant

Freya Bank is fictional. Every customer, debt and payment in this file is synthetic.

This file bundles four documents the bank sent us, unedited, in the order we received them:

- Part 1. Cover mail from the Head of Collections
- Part 2. Collections Policy, extract, version 3
- Part 3. Internal memo COL-2026-14, dated 1 October 2026
- Part 4. Code list for the call-result system

---

## Part 1. Cover mail

**From:** Margaret Okafor, Head of Collections, Freya Bank
**To:** Voice assistant vendor team
**Date:** Thursday 1 October 2026, 16:42
**Subject:** Early collections programme: policy, memo and codes for your build

Hello all,

Thanks for the kick-off call on Tuesday. As promised, here is everything you need to build the assistant for our early-collections programme. In short: we call customers who are between 1 and 45 days late on **one** product (a credit card, a personal loan or a car loan). The assistant finds the customer, checks who they are, tells them what is late, tries to get a promise to pay where it can, and closes the call with the right result code. One product per call in this programme, always. The multi-product programme is a separate project and is not part of this delivery, so you will not need the note function (`add_note`) at all; the NTE codes in the code list belong to that other programme.

A word on how to read the attachments, because people keep getting this wrong internally: the policy extract (Part 2) is the rulebook. The memo (Part 3) amends it, and each change in the memo applies from its own effective date, judged by the date of the call. Where this mail and the policy disagree, the policy as amended by the memo wins. I paraphrase a lot below; please don't build from my paraphrases. For example, I tend to say we give people "about two weeks" to pay. That is a figure of speech. The real limits are in the band table, in business days.

Your platform will receive five fields for every call and nothing else until the tools are called: `customer_id` (pass it on every tool call), `first_name` and `last_name` (the person to ask for), `title` (Mr or Ms; we address customers as title plus last name, so "Ms Costa", never "Maria"), and `now`, the current date and time of the call, for example `2026-10-14T11:00`. Every date rule uses `now`. Never the server clock.

A few things the compliance team asked me to stress, since they don't always come through in the policy wording:

- If anyone asks whether they are talking to a robot or an AI, the assistant says that it is Freya Bank's digital assistant, and carries on.
- If anyone asks whether the call is a scam, the assistant tells them they can verify the call by phoning Freya Bank's customer service number, and carries on.
- After a promise has been recorded, the customer must hear exactly this sentence, word for word: "You will receive a text message confirming this promise." Legal has signed off that wording and nothing else.
- When a family member tells us the customer has died, the assistant says "I am sorry for your loss." and nothing else, and ends the call.
- Relatives and anyone else who picks up get **nothing**. Until last year our human agents could leave the balance with a spouse. That stopped. A relative may not answer the security questions and may not be told anything about the account, even if they kindly offer to pay on the customer's behalf.
- Our agents are never to ask "how much can you pay?". The assistant proposes every amount itself.

Phone numbers, holidays and the rest are in the policy. Shout if anything is unclear.

Best regards,
Margaret

Margaret Okafor
Head of Collections, Freya Bank

---

## Part 2. Collections Policy, extract

**Document:** COL-POL-003, Early Collections (1 to 45 days past due), version 3
**Owner:** Collections Operations
**Approved:** 14 July 2026
**Scope of this extract:** sections 1 to 12, outbound calls by the digital assistant, single-product customers.

### §1 Definitions

1.1 *Business day*: Monday to Friday, except the bank holidays listed in §7.2.
1.2 *Today*: the calendar date of the call's `now` value.
1.3 *Past-due amount*: the `past_due` value returned for the product. Also called "the full amount".
1.4 *Floor*: the lowest amount the assistant may record as a promise (see §8.2).
1.5 *Result codes*: OUT-, RSN- and Q- codes are listed in the code list (Part 4). The assistant sends the system value given there, not the code itself.

### §2 Programme

2.1 The programme covers customers who are 1 to 45 days late on one product. The assistant finds the customer, checks identity, states the debt, gets a payment promise where it can, and closes the call with the correct result.

### §3 Opening and right-party contact

3.1 The first sentence of every call says that the caller is a digital assistant calling from Freya Bank and that the call is recorded. The words "collections", "debt" and "payment", and the name of the product, are not said before identity is verified. This applies to everyone who answers, relatives included.

3.2 The assistant then asks: "Am I speaking with {title} {last_name}?"

3.3 Only "yes", "that's me", "speaking" or the customer's own name counts as confirmation. "Hello", "go ahead" and "who is this" do not. The assistant asks once more. If it is still unclear after the second ask, the call is closed with OUT-NRC / RSN-UNC. If the person asks a question, the assistant answers it first (§3.4, §11.5); the ask that follows the answer is the second ask.

3.4 If asked whether they are speaking to a robot or an AI, the assistant says it is Freya Bank's digital assistant and continues.

### §4 Third-party contact

4.1 If someone other than the customer answers, the assistant does not say why it is calling and says nothing beyond the opening sentence of §3.1. It asks when the customer can be reached.

4.2 A callback may be booked for today or the next business day, later than `now`, inside the callback window of **10:00 to 18:00**, both ends included. The assistant books it with `schedule_callback` (date and time) and closes with OUT-NRC / RSN-CBK.

4.3 If the person offers a day or a time outside that, the assistant asks once for another time. If the second answer is also outside it, no callback is booked and the call is closed with OUT-NRC / RSN-NCB.

4.4 If the person says the number does not belong to the customer: OUT-NRC / RSN-WRN.

4.5 If the person says the customer has died, the assistant says "I am sorry for your loss.", asks nothing else, and closes with OUT-NRC / RSN-DEC.

4.6 A relative may not answer the security questions and may not be told anything about the account, even if they offer to pay.

### §5 Identity verification

5.1 Two security questions, one at a time, in this order: (a) date of birth, (b) the last four digits of the phone number on file. Each answer is checked with `verify_identity`. A date of birth is sent as `YYYY-MM-DD`, however the customer said it; the service rejects anything it cannot read as a date. A date given only as numbers is read as day, then month, then year.

5.2 A wrong answer may be asked again. Three wrong answers in total end the check, whichever question they were on.

5.3 If the customer gives day and month the wrong way round, `verify_identity` returns the hint `day_month_swapped`. The assistant asks the customer to say the month as a word. This retry is not a wrong answer.

5.4 After the third wrong answer the assistant does not state the debt. It tells the customer to use the mobile app or a branch, and closes with OUT-NVF / RSN-IDF.

5.5 If the customer does not want to answer, the assistant explains once that the questions protect their account. If they decline again, it closes with OUT-NVF / RSN-IDD. Asking what the call is about instead of answering counts as declining. A second refusal, or a second such question, closes the call.

### §6 Stating the debt

6.1 When both questions have passed, the assistant calls `get_account`.

6.2 It then says that it is calling from the collections team about a late payment, names the product in words ("credit card ending 4821", "personal loan" or "car loan"), and states the past-due amount and the number of days late.

### §7 Calendar and deadlines

7.1 Business days are Monday to Friday, excluding the holidays in §7.2.

7.2 Freya Bank holidays (dates in this table are the only non-weekend closures):

| Holiday | Date |
|---|---|
| Founders' Day | Monday 26 October 2026 |
| Remembrance Day | Wednesday 11 November 2026 |
| Thanksgiving | Thursday 26 November 2026 |
| Christmas Day | Friday 25 December 2026 |
| New Year's Day | Friday 1 January 2027 |

7.3 The **deadline** for a promise depends on how late the customer is. Business days are counted from the day after today.

| Days past due | Band | Latest promise date (deadline) | Persuasion attempts |
|---|---|---|---|
| one to seven | Early (E1) | the twelfth business day after today | one |
| eight to forty-five | Late (E2) | the tenth business day after today | two |

7.4 A promise date must be today or later, a business day, and not after the deadline.

7.5 If the customer names a weekend day or a holiday that is not after the deadline, the assistant offers the next business day. If the named day is after the deadline, §7.8 applies.

7.6 If the customer gives a vague period ("next week", "end of the month", "when my salary comes"), the assistant asks once for the exact day. If they still give none, it proposes the deadline.

7.7 "Next <weekday>" means that weekday in the following calendar week. "This <weekday>" means the one in the current week. So "next Friday" said on a Friday is the Friday of the following week.

7.8 If the customer asks for a date after the deadline, the assistant says the latest date it can record is the deadline and offers it. If the customer refuses the deadline, that is a flat refusal (§9.3).

### §8 Amounts

8.1 The assistant asks for the full past-due amount first. It never asks "how much can you pay?". The assistant proposes every amount.

8.2 Floors by product type:

| Product type (system value) | Floor | Example from the training pack |
|---|---|---|
| Credit card (`credit_card`) | the minimum payment due (`minimum_payment`) | USD 420.00 past due, floor USD 126.00 |
| Personal loan (`personal_loan`) | one contractual instalment (`instalment_amount`) | USD 310.50 past due, floor USD 103.50 |
| Car loan (`car_loan`) | one contractual instalment (`instalment_amount`) | USD 1,250.00 past due, floor USD 400.00 |

The examples are illustrations only. The assistant always uses the values returned by `get_account`.

8.3 If the customer says the full amount is too much, the assistant offers the floor, once, and says that the rest stays overdue. If the customer refuses the floor, that is a flat refusal (§9.3). Attempt two may name the floor again, on the deadline.

8.4 If the customer proposes an amount from the floor up to the full amount, both included, the assistant accepts it. Below the floor, it says the amount cannot be recorded and offers the floor once. If the customer does not accept the floor, that is a flat refusal (§9.3).

### §9 Obtaining the promise

9.1 The first ask is: "Can you make this payment today?"

9.2 A date or an amount the customer proposes is never a refusal. It is handled under §7 and §8.

9.3 A flat refusal or a non-answer uses one persuasion attempt. A no to paying today, with no date and no amount, is a flat refusal. Attempt one is for the full past-due amount, or for the floor if the customer already said the full amount is too much.

| Attempt | Bands | Offer |
|---|---|---|
| One | E1 and E2 | the last business day of this week; if today is that day, the last business day of next week |
| Two | E2 only | the floor amount, on the deadline |

9.4 When the attempts are used up, the assistant stops. It does not repeat an offer the customer already refused. Close: OUT-NPR / RSN-REF.

9.5 If the customer mentions illness, a death in the family or job loss, the assistant says one short sentence of sympathy and makes no persuasion attempt. It offers to connect them with the customer support team. If they accept: `transfer_to_agent` with Q-SUP, close OUT-TRF / RSN-SUP. If they decline: OUT-NPR / RSN-HRD. This section takes precedence over §9.3 and §11.3. If the customer still names a date or an amount themselves, the promise is recorded under §7 and §8.

9.6 The assistant never offers a discount, a waiver, an instalment plan or any term that is not in this policy.

### §10 Confirmation and recording

10.1 The assistant reads the product, the amount and the date back and asks "Do you confirm?". It calls `create_promise` only after a clear yes.

10.2 If the customer changes the date or the amount at this step, the new value is checked against §7 and §8 and read back again.

10.3 One promise per product. A recorded promise cannot be changed or cancelled in the same call; if asked, the assistant says the customer can change it in the mobile app.

10.4 The assistant says the promise is recorded only after `create_promise` returns `ok: true`. If it fails, it tries once more. If it fails again, it says it could not record the promise and closes with OUT-NPR / RSN-SVC.

10.5 After a recorded promise, the assistant says: "You will receive a text message confirming this promise."

### §11 Other customer statements

11.1 "I already paid": the assistant says that payments can take one business day to appear, takes no promise, and closes with OUT-PDA.

11.2 "This debt is not mine" or "I never had this product": the assistant does not argue and takes no promise. Close: OUT-NPR / RSN-DSP. A claim that the product was closed or paid off in the past is a dispute. §11.1 covers only a payment of this past-due amount.

11.3 A request for a new payment plan or lower instalments: the assistant does not describe a plan. `transfer_to_agent` with Q-RST, close OUT-TRF / RSN-RST.

11.4 A request for a human: the assistant asks once whether it can help first. If they insist: `transfer_to_agent` with Q-GEN, close OUT-TRF / RSN-HUM.

11.5 "Is this a scam?": the assistant says they can verify the call by phoning Freya Bank's customer service number, and continues.

11.6 A question the assistant cannot answer from the tools: it says it does not have that information. It does not invent figures, dates or reasons.

11.7 If the customer says twice that they do not want to talk: OUT-NPR / RSN-REF. Before identity is verified, the same customer is closed with OUT-NVF / RSN-IDD. §11.4 applies both before and after verification.

### §12 Closing

12.1 Every call ends with exactly one `close_call`, carrying a result and, where the table lists one, a reason. It is the last tool call.

| Result | Reasons | When |
|---|---|---|
| OUT-PRM | none | at least one promise was recorded |
| OUT-PDA | none | §11.1 |
| OUT-TRF | RSN-RST, RSN-HUM, RSN-SUP | §11.3, §11.4, §9.5 |
| OUT-NPR | RSN-REF, RSN-HRD, RSN-DSP, RSN-SVC | §9.4 and §11.7, §9.5, §11.2, §10.4 |
| OUT-NVF | RSN-IDF, RSN-IDD | §5.4, §5.5 |
| OUT-NRC | RSN-CBK, RSN-NCB, RSN-WRN, RSN-DEC, RSN-UNC | §4.2, §4.3, §4.4, §4.5, §3.3 |

If a transfer follows a recorded promise, the call is closed as OUT-TRF with that transfer's reason.

12.2 The assistant thanks the customer and says goodbye before `close_call`.

---

## Part 3. Internal memo

**Memo COL-2026-14**
**From:** Margaret Okafor, Head of Collections, on behalf of the Collections Risk Committee
**To:** Collections Operations; digital assistant vendor
**Date:** 1 October 2026
**Subject:** Changes to COL-POL-003 v3 agreed at the September committee

The committee met on 29 September 2026 and agreed the following. Until version 4 of the policy is published, this memo amends version 3. Each change applies to calls whose date (`now`) is on or after its effective date. Calls before an effective date follow the policy as it stood.

**Item 1. Late band (E2) deadline.** The latest promise date for E2 customers (eight to forty-five days past due) is shortened from the tenth to the **seventh** business day after today. Effective for calls from Monday 5 October 2026. E2 still gets two persuasion attempts.

**Item 2. Callback window.** The callback window in §4.2 now closes at **19:00** instead of 18:00. It opens at 10:00 as before, both ends still included, and the day rule (today or the next business day, later than `now`) does not change. Effective for calls from Monday 12 October 2026.

**Item 3. Early band limits (not approved).** Operations proposed moving the E1/E2 boundary from 7 to 10 days past due. The committee did **not** approve this. Bands stay at one to seven (E1) and eight to forty-five (E2).

**Item 4. Christmas Eve.** Thursday 24 December 2026 is **not** a bank holiday. Branches close early, but it is a business day. The holiday table in §7.2 stands as published.

**Item 5. Early band (E1) deadline, from mid-November.** For calls made **on or after Monday 16 November 2026**, the latest promise date for E1 customers is shortened from the twelfth to the **tenth** business day after today. E1 still gets one persuasion attempt. This change is decided by the date of the call, not by the promise date: a call made before 16 November 2026 keeps the twelfth business day, even if that deadline falls on or after 16 November 2026.

Questions to Collections Operations.

M. Okafor

---

## Part 4. Code list: call-result system (extract)

The policy refers to results by internal code. The tools take the **system value**. Send the system value exactly as written in this table.

**Call outcomes** (`close_call.outcome`)

| Code | Meaning | System value | Status |
|---|---|---|---|
| OUT-PRM | Promise to pay recorded | `promise` | active |
| OUT-PDA | Customer states already paid | `paid` | active |
| OUT-TRF | Handed to a colleague | `transferred` | active |
| OUT-NPR | Verified, no promise | `no_promise` | active |
| OUT-NVF | Identity not verified | `not_verified` | active |
| OUT-NRC | Customer not reached | `not_reached` | active |
| OUT-VML | Voicemail left | `voicemail` | retired 2025, never send |

**Reasons** (`close_call.reason`; OUT-PRM and OUT-PDA take no reason)

| Code | Meaning | System value | Used with |
|---|---|---|---|
| RSN-RST | Restructuring request | `restructuring` | OUT-TRF |
| RSN-HUM | Asked for a person | `human` | OUT-TRF |
| RSN-SUP | Hardship, accepted support | `support` | OUT-TRF |
| RSN-REF | Refused | `refused` | OUT-NPR |
| RSN-HRD | Hardship, declined support | `hardship` | OUT-NPR |
| RSN-DSP | Disputes the debt | `dispute` | OUT-NPR |
| RSN-SVC | Promise could not be recorded | `service_error` | OUT-NPR |
| RSN-IDF | Failed the security questions | `failed` | OUT-NVF |
| RSN-IDD | Declined the security questions | `declined` | OUT-NVF |
| RSN-CBK | Callback booked | `callback` | OUT-NRC |
| RSN-NCB | No callback possible | `no_callback` | OUT-NRC |
| RSN-WRN | Wrong number | `wrong_number` | OUT-NRC |
| RSN-DEC | Customer deceased | `deceased` | OUT-NRC |
| RSN-UNC | Could not confirm who answered | `unclear` | OUT-NRC |
| RSN-LGL | Legal hold | `legal_hold` | retired 2025, never send |

**Transfer queues** (`transfer_to_agent.queue`)

| Code | Team | System value |
|---|---|---|
| Q-RST | Restructuring team | `restructuring` |
| Q-GEN | General customer service | `general` |
| Q-SUP | Customer support (hardship) | `support` |

**Note reasons** (`add_note.reason`): multi-product programme only, not used in this programme

| Code | System value |
|---|---|
| NTE-REF | `refused` |
| NTE-HRD | `hardship` |
| NTE-DSP | `dispute` |
| NTE-PDA | `paid` |
| NTE-SVC | `service_error` |
