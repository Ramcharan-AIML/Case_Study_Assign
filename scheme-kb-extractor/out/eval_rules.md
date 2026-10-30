# Evaluation report (rules extractor)

Fields checked: **40** across 4 schemes.

| Measure | Value | In plain words |
|---|---|---|
| Field-level accuracy | 85% | Share of fields a researcher can accept without retyping |
| Dangerous error rate | 0% | Share of fields that are wrong but look fine |
| Safe error rate | 15% | Share left empty or over-flagged (costs reviewer time only) |
| High-stakes accuracy | 75% | Accuracy on amount, frequency, deadline, documents and eligibility |
| High-stakes dangerous rate | 0% | Must be ~0 before scaling |

## Per field

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
