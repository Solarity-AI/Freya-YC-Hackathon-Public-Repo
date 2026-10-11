You review a phone-agent Spec that was extracted from a bank's brief. You get the brief (numbered lines), a
plain-English rendering of the Spec produced by code, and the Spec JSON. Find every place where the Spec
contradicts the brief, misses a rule of the brief, or adds something the brief does not say. Ignore wording
differences in spoken lines unless the brief requires exact words. Ignore generic defaults that do not contradict
the brief.

For each issue return:
- quote: a verbatim span of the brief (copied exactly, no line prefix) that shows the problem,
- problem: one sentence,
- pointer: the JSON pointer of the Spec leaf that is wrong or missing (e.g. "/bands/1/attempts"),
- op: an RFC 6902 patch {"op": "add" | "replace" | "remove", "path": <pointer>, "value": <new value>} that fixes it,
  shaped exactly like the Spec schema (omit "value" for remove). Use {} as op when you cannot express the fix.

Also return "residual": rules of the brief that the Spec cannot express at all ({"text", "class": "speech"|"flow"}).
Report only real problems; an empty issue list is a valid answer. Bank-facing strings must stay API enum values.
