Review this code and find up to 3 places where it is slower or clumsier than necessary: worse time complexity than needed, repeated work, the wrong data structure, or an unidiomatic pattern that hurts performance or clarity (for example a nested loop that could be a hash-map lookup, or a membership test on a list inside a loop).

Language: $language
Problem / file: $problem_title

CODE (line numbers are NOT part of the code):
$numbered_code

For each place:
- "quote": copy the exact line or lines from the code, character for character, WITHOUT the line numbers. Keep it short (1 to 6 lines). If you cannot quote it exactly, leave that place out.
- "issue": a short label, e.g. "Nested loop over the same array".
- "why": one or two sentences on why it is slow or clumsy.
- "complexity_before" / "complexity_after": big-O, e.g. "O(n^2)" and "O(n)", or null if complexity is not the point.
- "suggestion": the better approach in plain English.
- "replacement": $replacement_rule
- "confidence": "high", "medium" or "speculative".

Only report real improvements. If the code is already good, return an empty list. Do not report style nitpicks.

Return a JSON object with a "suggestions" list.
