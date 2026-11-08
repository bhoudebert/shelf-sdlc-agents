---
applyTo: "test/**,**/*.test.ts,**/*.test.js,**/*.spec.ts"
---

# Tests

- One behaviour per test, named after the behaviour ("rejects a duplicate ride"), not the function.
- Deterministic: no clock, network, randomness or ordering assumptions without a fake.
- Never call a paid or external service for real; use the fakes in the test helpers.
- A bug fix starts with a test that fails for the right reason.
- A test that needed a new expected value is a sign that behaviour changed: check the spec or decision record.
