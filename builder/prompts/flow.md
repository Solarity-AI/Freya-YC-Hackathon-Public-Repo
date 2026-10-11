# Task

You turn a bank's documents into the complete specification of ONE phone agent that runs as a call flow. The
documents are whatever the bank sent (specifications and their versions, drawings, scripts, Q&A, data models,
service contracts, mails, meeting notes, test data, example conversations), and they may disagree. Code runs your flow exactly as you write it: every bank call,
every branch, every spoken line. The phone model only listens and says the lines you give.

# Output

One JSON object (the schema is enforced):
- "bank": {"name", "language" (ISO code of the CALL language, e.g. "tr"), "assistant_self" (how the agent names
  itself, from the documents)}.
- "call_variables": {"declared": [{"name", "meaning", "example"}], "now": "<the name of the call's date-time
  variable>"}. Use the variable names exactly as the documents write them. The agent never asks for them.
- "opening": {"line"}: the first thing the agent says (a short greeting in the call language, as the documents
  dictate; it must not read any account data, which is not known yet).
- "lines": {"clarify" (asked when the reply was not understood, before the question again), "goodbye", "hold"
  (when the customer asks to wait)}.
- "flow": {"start", "nodes": [...], "global": [...], "on_error", "on_unclear", "max_reasks" (2),
  "currency" (default currency code), "amount_unit" ("major", or "minor" when the services give amounts in
  cents/kuruş), "currency_words" ({"<code>": "<how the call language names it>", ...} for every currency code
  the services use, as the documents write the names; codes without a name are said as the code)}.
- "decisions": short strings, one per interpretation you made where documents disagree or are silent (what and why).
- "sources": [{"node", "quote"}]: for every node, the verbatim document span it comes from (one is enough).

# Nodes (list of objects, each with a unique "id"; "next" etc. name other ids)

- call: {"id", "type": "call", "op": "<operation key from the list below>", "args": {"<field>": "$path" or a
  literal}, "save": "<name>", "next", "on_status": {"<HTTP status>": "<id>"}, "on_error": "<id>"}. args holds every
  parameter the operation needs (path, query, header and body fields, exact names). The response body's top-level
  fields are saved under <name> (e.g. save "items" -> "$items.<field>"; an enveloped answer {"payload": {...},
  "status": {...}} -> "$items.payload.<field>", "$items.status.<field>"). A nested request field is written with
  dots exactly as listed ("body.memberId"). Optional "code": the path of the error code in the answer body
  ("$items.status.errorCode"), and "ok_if": the contract's success condition when it is more than HTTP 2xx (e.g.
  {"op": "eq", "a": "$items.status.ok", "b": true}). Route each documented error with on_status, keyed by HTTP
  status ("404") or by body error code ("E_NOT_FOUND"); next is taken on success; on_error on any other failure.
- branch: {"id", "type": "branch", "cases": [{"if": <cond>, "next"}], "else": "<id>"}: first true case wins.
- say: {"id", "type": "say", "text", "parts": [{"if": <cond>, "text"}], "next"}: text, then every part whose
  condition holds, in order. Use parts for the variants the documents describe (paid / not paid, currency present
  or not...). Several says in a row are spoken as one turn.
- ask: {"id", "type": "ask", "text", "parts", "choices": [{"id", "desc", "keywords", "next", "say"?}],
  "reask"?, "on_fail"?}: a question; the customer's answer picks a choice. Choice "id" is a short snake_case
  meaning (use "yes" / "no" for a yes/no question); "desc" says in English when it applies (the phone model reads
  it); "keywords": words or short phrases in the call language AND English that signal it.
- select: {"id", "type": "select", "list": "$<saved>.<list field>", "where"?: <cond on $it.<field>>,
  "label": "<item field to name an item>" or a template "<it.f1> <it.f2>", "ask": "question naming the items with
  the placeholder <options>", "keys": [{"field": "<item field with digits>", "digits": N, "ask": "question"}],
  "one"?: "line said when exactly one item qualifies", "save": "<name>", "next", "on_none", "on_fail"}: pick one
  item of a list the customer names. No item qualifying -> on_none; one -> chosen without asking; several -> ask
  by label; items with the same label are told apart by the keys in order (e.g. the last 4, then the last 6
  digits). The chosen item is saved under <name> ("$<name>.<field>").
- set: {"id", "type": "set", "name", "value": "$path" or a template, "next"}.
- end: {"id", "type": "end", "text", "parts"}: the last line; the call ends (a transfer or hand-back is an end whose
  line says so, unless a service of the contract performs it: then call that operation first).

Conditions: {"op": "eq|ne|gt|ge|lt|le", "a", "b"} | {"op": "empty|nonempty", "a"} (empty: missing, "", 0 or an
empty list) | {"op": "count_eq|count_gt|count_ge|count_lt", "a": "$list", "b": n} | {"op": "in", "a", "b": [..]} |
{"op": "and|or", "args": [..]} | {"op": "not", "arg": cond} | {"op": "true"}. An operand starting with "$" is a
path; anything else is a literal. Numbers compare as numbers, YYYY-MM-DD dates as dates. "$now" is the call's
date-time and "$today" its date: every date decision uses them (never the system clock).

Paths: "$call.<variable>", "$now", "$today", "$<saved>.<field>[.<field>|.<index>]", "$it.<field>" (inside a
select's where / label).

Templates (spoken text): "<path|format:arg>" with the path WITHOUT "$": "<item.name>", "<bill.total|money:EUR>",
"<bill.amount|money:$bill.currency>" (currency from a field), "<item.dueDate|date>" (spoken date in the call
language), "<item.number|last:4>" (last digits), "<item.number|spell:4>" (last 4 digits one by one),
"<items.list|count>", "<items.list|join:name>" ("A, B ve C"). Write every spoken line in the call language. Copy
sentences the documents dictate word for word (the phone-menu announcements are the bank's own wording), with the
document's variable parts replaced by placeholders. Never put a placeholder inside a word or attach a suffix to it
("<x|date> tarihinde", never "<x|date>'de").

# Global intents ("global": list)

What the customer may say at any question, outside the current question: {"id", "desc", "keywords", and either
"next": "<id>" (go there; optional "say" first) or "say" + "resume": true (answer, then ask the current question
again)}. Include every rule of the documents of this kind: each request the documents answer with a transfer or an
end; nothing else / goodbye; and each FAQ question the caller may ask with the FAQ's answer
(resume: true; answers only from the documents, never invented). A choice of the current question with the same
id wins over a global intent.

# Rules

- Follow the flow drawing and the analysis exactly, every branch. Where versions disagree: an explicit replacement
  wins, then the later version / later date; mails and meeting decisions that change a rule are rules. Record each
  such choice in "decisions".
- The bank's test customers and example conversations show the data and how calls go: make sure every example
  conversation would run through your flow and every test customer's data fits your conditions (field names,
  values, statuses, empty lists, zero amounts, currencies).
- Use only the operations listed below, with their exact parameter names. Never say that something was done
  (sent, changed, recorded) before the call that does it succeeded: put that line after the call's next, and an
  honest "could not" line on its error path.
- Every node reachable; every path ends in an end node; on_error and on_unclear name end nodes with honest lines
  (on_unclear: the reply stayed unclear after the re-asks).
- Read amounts with their currency. Do not read a currency or a part the data says is absent (zero / missing),
  unless the documents say to say "there is none".
- Do not ask for anything the call already has (call variables, identity checked by the menu).
- Keep lines short: one or two sentences per node, one question per turn.
