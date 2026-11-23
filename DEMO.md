# 5-minute demo script

1. **Load demo document.** Point out colour = type, underline = confidence, red outline = ambiguous.
   Note the Order ID is *not* flagged (checksum look-alike).
2. **Approve high-confidence**, then review the remaining items with `A` / `R`. Show "Approve all similar".
3. **Export.** Show the green "verified" line.
4. **Inspect export.** Type `Richa`, `411001`, the Aadhaar number: 0 in every source.
   Then type `Meridian` (not redacted) to show the search is real. Show the SHA-256 and file structure.
5. **Generate summary.** Show **High** risk and the attacker query. Click **Generalise**; risk drops to Low,
   changed words are listed. Mention the document-body warning and that this is a heuristic.
6. **Report.** Open it: counts and checksum, no removed text.
7. Close with limitations (no OCR, heuristic risk).

Likely judge questions: *"How is the risk computed?"* Rule-based on which detail types co-occur; no population data, so no count.
*"Is it really irreversible?"* Page is pixels; only placeholders remain as text; searched with 4 extractors + raw streams.
