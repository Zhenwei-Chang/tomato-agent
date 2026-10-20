# Offline Demo Smoke Record

Verified on 2026-10-19 with Python 3.12.9. No provider credential was configured or used.

## Fixture validation

```text
All recorded replay fixtures are valid.
```

## Comprehensive terminal replay

```text
[RECORDED_REPLAY] Six-tool evidence workflow
Scenario: comprehensive
Status: PARTIAL | Reliability: LOW

Tool calls:
  1. get_growth_context -> partial [plant]
  2. get_sensor_history -> success [greenhouse]
  3. predict_height_t7 -> success [plant]
  4. find_similar_cases -> error [plant] (NO_RELIABLE_CASES)
  5. retrieve_water_fertilizer_knowledge -> success [knowledge]
  6. assess_prediction_reliability -> success [plant]
```

## Local HTTP smoke

The server was started on an alternate localhost port for the check.

```json
{
  "index_status": 200,
  "index_has_replay": true,
  "fixture_status": 200,
  "fixture_has_six_tool": true
}
```

The server was stopped immediately after the check.
