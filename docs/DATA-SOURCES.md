# Canonical data-source policy

The Personal Performance & Health OS must keep data provenance, licensing, freshness, and confidence explicit. External data is never copied into the canonical knowledge base without a source-specific license decision.

## Personal health and activity

- **Android Health Connect** — canonical Android interchange layer for user-authorized health and fitness records. Store source application/data-origin metadata and preserve differential-change history.
- **FIT files** — `fitdecode` remains the default permissive parser. The official Garmin FIT SDK may be used as an optional interoperability validator when its protocol licence is acceptable for the intended deployment.
- **CSV/GPX/manual import** — accepted through normalized adapters; imported values must keep import timestamp, original source, unit and raw hash.

## Nutrition

- **USDA FoodData Central** — canonical open nutrient reference and first choice for machine integration. Data is public domain/CC0. API credentials must stay outside the repository.
- **TACO / NEPA-Unicamp** — preferred Brazilian composition reference when an equivalent Brazilian food exists. Reuse must preserve source citation and the exact source edition.
- **Open Food Facts API v3** — complementary source for packaged products/barcodes. Preserve Open Database Licence attribution/share-alike obligations and source reliability metadata; community-entered values are not treated as analytically equivalent to laboratory reference tables.
- **TBCA / USP-FoRC** — high-value Brazilian reference but restricted for automated redistribution/commercial reuse. Do not mirror or redistribute the database in this repository. Use only in permitted personal/reference workflows unless explicit commercial permission is obtained.

## Exercises and movement taxonomy

- **Internal canonical exercise registry** remains the source of truth for prescriptions because it includes environment, space, noise, equipment, fixation points, fatigue, impact, skill, strength, power, conditioning, unilateral status, progressions, regressions and alternatives.
- **wger REST API** may be used as a discovery/reference source. Do not fork or copy wger application code into Health OS: wger code is AGPL. Exercise/ingredient seed data is CC-BY-SA and requires attribution/share-alike handling if incorporated.
- Research AI may discover additional exercise datasets, but none become canonical until licence, source quality and field compatibility are audited.

## Evidence and coaching knowledge

Research AI and Segundo Cérebro provide evidence packages. Priority: ACSM, NSCA, TSAC-F/H2F, sport governing bodies, systematic reviews, meta-analyses, peer-reviewed research, and authoritative technical books. Every material claim must be tagged as `EVIDENCE`, `COACHING_PRACTICE`, or `HYPOTHESIS`.

## Source-quality contract

Every normalized external record should retain at least:

- `source_id`
- `source_type`
- `source_record_id`
- `source_url` or canonical reference when allowed
- `observed_at`
- `retrieved_at`
- `raw_hash`
- `license_id`
- `quality`
- `confidence`
- `metadata`

Source priority never authorizes silent overwrites. Corrections create a new provenance-aware record or a tombstone/update event according to the entity policy.
