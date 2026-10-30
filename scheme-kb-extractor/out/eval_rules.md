# Evaluation report (rules extractor)

Fields checked: **40** across 4 schemes.

| Measure | Value | In plain words |
|---|---|---|
| Field-level accuracy | 85% | Share of fields a researcher can accept without retyping |
| Dangerous error rate | 0% | Share of fields that are wrong but look fine |
| Safe error rate | 15% | Share left empty or over-flagged (costs reviewer time only) |
| High-stakes accuracy | 75% | Accuracy on amount, frequency, deadline, documents and eligibility |
| High-stakes dangerous rate | 0% | Must be ~0 before scaling |
| Conflict recall | 75% | Of 4 real disagreements, how many were shown |
| Grounding rate | 100% | Filled values whose quote really is in the source |

## Ready to scale to 5,000 schemes? **NOT YET**

| Check | Rule | Actual | Result |
|---|---|---|---|
| Test set is big enough | n_schemes >= 100 | 4 | FAIL |
| No dangerous errors on high-stakes fields | high_stakes_dangerous_rate <= 0.01 | 0% | PASS |
| Every value has a real quote | grounding_rate >= 1.0 | 100% | PASS |
| Conflicts are caught | conflict_recall >= 0.95 | 75% | FAIL |
| Checking beats typing | accuracy >= 0.8 | 85% | PASS |

## By document type

| Document type | Fields | Accuracy | Dangerous | Safe errors |
|---|---|---|---|---|
| Press note | 10 | 100% | 0 | 0 |
| Scanned PDF | 10 | 40% | 0 | 6 |
| Text PDF | 10 | 100% | 0 | 0 |
| Web page | 10 | 100% | 0 | 0 |

## By field

| Field | n | Accuracy | Dangerous | Safe errors |
|---|---|---|---|---|
| scheme_name | 4 | 100% | 0 | 0 |
| department | 4 | 100% | 0 | 0 |
| benefit_type | 4 | 100% | 0 | 0 |
| benefit_amount | 4 | 75% | 0 | 1 |
| benefit_frequency | 4 | 75% | 0 | 1 |
| eligibility | 4 | 75% | 0 | 1 |
| documents_required | 4 | 75% | 0 | 1 |
| how_to_apply | 4 | 75% | 0 | 1 |
| deadline | 4 | 75% | 0 | 1 |
| official_link | 4 | 100% | 0 | 0 |

## Every field that was not correct

| Scheme | Field | Outcome | Draft said | Truth |
|---|---|---|---|---|
| SCH003 | benefit_amount | **missed** | not_found | conflict |
| SCH003 | benefit_frequency | **missed** | not_found | found |
| SCH003 | eligibility | **missed** | not_found | found |
| SCH003 | documents_required | **missed** | not_found | found |
| SCH003 | how_to_apply | **missed** | not_found | found |
| SCH003 | deadline | **missed** | not_found | found |
