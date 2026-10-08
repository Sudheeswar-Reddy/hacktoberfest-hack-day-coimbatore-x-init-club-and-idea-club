Decide whether this person is genuinely stuck or is working productively.

Problem: $problem_title
Platform: $platform ($mode mode)

Measured by the activity recorder (facts, do not question them):
- Minutes on this problem in the last 30 min, including detours to help sites: $minutes
- Round trips problem -> help site (search / Q&A / AI chat) -> back: $loops
- Typing rate on the problem itself: $kpm keystrokes per minute
- Detection rules that fired: $rules

Recent activity, oldest first (app | site | window title | minutes | keystrokes):
$frames

How to judge:
- Long time alone is NOT enough. Steady typing with occasional lookups is normal work.
- Signs of being stuck: repeated trips to help sites for the same problem, very low typing for a long time, searching the same idea again and again, switching between AI chat and the problem.
- If unsure, prefer "stuck": false. A false alarm interrupts the user.

Return "stuck" (true/false) and a one-sentence "reason" that cites the measurements above.
