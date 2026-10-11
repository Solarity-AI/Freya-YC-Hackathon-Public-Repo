# Task

You read a bank's SERVICE CONTRACT: the description of the web services (operations) that a phone agent calls
during a call. The contract may be an endpoint table, a Word/PDF/Markdown description, field lists, enum lists and
error-code tables, in any language (often Turkish). Convert it into the operation list described by the schema.
A program turns your answer into an OpenAPI 3 document and checks it against the contract text, so:

- Copy every operation name, path, field name and enum value EXACTLY as the contract writes it (same spelling,
  same case, same accents, same underscores). Never translate, rename or invent a field, a path or a value.
- List EVERY operation and EVERY path the contract mentions. Do not add operations the contract does not have.
- `method`: the HTTP method the contract gives; POST when it gives none. `path`: the path as written (starting
  with "/"); when the contract gives only an operation name, use "/" + that name.
- `request`: every input field (body, query or path parameter alike) with its type, whether it is required,
  its enum values (exactly as written), its format (`date` for a calendar day, `date-time` for a timestamp, else
  ""), and its description (copy the contract's own words, including any value format such as YYYY-MM-DD,
  DD.MM.YYYY or HH:MM, and any "required only when ..." rule).
- `response`: every field of the successful answer. A list of records (for example the customer's products or
  accounts) is a field of type "array" whose `items` are the record's fields. A nested object is a field of type
  "object" whose `fields` are its children. Do not invent a success flag when the contract has none.
- `success`: the response field that says the call succeeded and the value(s) that mean success, copied exactly;
  {"field": "", "values": []} when success is only the HTTP status.
- `errors`: the error codes / HTTP statuses the contract lists for this operation and what each means.

# Roles

The phone agent's engine knows these service roles (`tool`); give each operation the one it plays, or "other":
- verify_identity: checks the caller's identity answers (one call per question, or all answers in one call).
- get_account: reads the customer's debt / account / products / statement.
- create_promise: records the customer's promise to pay (an amount on a date for a product).
- add_note: adds a note / comment to the customer record.
- schedule_callback: books a call back at a date/time.
- transfer_to_agent: hands the call to a human agent / team / queue.
- close_call: records the call's outcome / disposition and ends it.
Give at most one operation each role, except verify_identity when the contract has one operation per question.

Field `role` (use "" when none fits; never two fields of one operation with the same role):
- request: customer (the customer's id / number), selector (which identity question is being answered),
  answer (the answer to it), product (which product / account / card), amount, date, time, datetime, reason
  (a reason / code from a list), text (free note text), queue (team / queue to transfer to), outcome (call result).
- response: s (the success flag / status), err (error message), verified (this answer was correct),
  left (attempts left), all (every identity question passed), hint (a hint about a wrong answer),
  products (the list of the customer's products / accounts), pid (the id of the created record).
- array item fields of the products list: id (the product id), type (the product type), past_due (the amount the
  customer owes now / overdue), days_late (days overdue).

# Output

One JSON object matching the schema. `notes`: short strings for anything in the contract you could not express
(rate limits, headers, authentication, ordering rules between operations).

# Example (synthetic, unrelated to any real bank)

Contract text: "POST /odeme-plani/kaydet — girdi: `musteri_kodu` (zorunlu), `plan_tipi` (AYLIK | HAFTALIK),
`ilk_tarih` (GG.AA.YYYY). Yanıt: `durum` = TAMAM veya RED."
-> {"name": "kaydet", "method": "POST", "path": "/odeme-plani/kaydet", "tool": "create_promise", "request": [
{"name": "musteri_kodu", "type": "string", "required": true, "role": "customer", ...}, {"name": "plan_tipi",
"enum": ["AYLIK", "HAFTALIK"], ...}, {"name": "ilk_tarih", "description": "GG.AA.YYYY", "role": "date", ...}],
"response": [{"name": "durum", "type": "string", "enum": ["TAMAM", "RED"], "role": "s"}],
"success": {"field": "durum", "values": ["TAMAM"]}, ...}
