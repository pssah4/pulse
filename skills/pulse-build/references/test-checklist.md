# Test checklist

## Every test

- **AAA:** arrange inputs, fixtures, and mocks; act by invoking the unit
  once; assert on the return value, the state change, or the thrown
  error. One behavior per test, named after the behavior, not the method.
  Match the project's assertion style; no `// Arrange` comments unless
  the project has them.
- **FIRST:** fast (under 1 s per unit test), independent, repeatable,
  self-validating, timely.
- **Mocks:** external dependencies only (APIs, file system, DB), never
  the unit under test. Prefer dependency injection over global mocks and
  reuse the project's mock patterns.
- **Unit tests** for public functions with logic, utilities, data
  transformations, error handling. Skip trivial getters, setters, and
  pass-throughs.
- **Integration tests** use real dependencies where possible (a test DB
  or an in-memory one) and mock only external services. Each test owns
  its state and teardown, uses realistic data (not `foo`, `bar`, `test`),
  and has a timeout when it is async. Shared setup only for shared
  resources.
- **File names** follow the project. If it has no pattern:
  `{module}.test.ts` or `{module}.spec.ts` for unit tests,
  `{module}.integration.test.ts` for integration tests, next to the
  source or under `tests/`.

## Coverage targets

Guidelines; targets in the project's AGENTS.md, CLAUDE.md, or the spec
win.

| Metric | Target | Minimum |
|--------|--------|---------|
| Line coverage | 85% | 70% |
| Branch coverage | 80% | 65% |
| Function coverage | 90% | 75% |

## Per function or method

### Happy path

- Normal call with valid input -> expected result
- Different valid input variants (where applicable)

### Edge cases

- Empty input (empty string, empty array, empty object)
- null / undefined / None as input
- Boundaries (0, -1, MAX_INT, an empty array of length 0)
- A single element (array with one item, string with one char)
- Unicode and special characters in strings
- Very large inputs (where performance matters)

### Error cases

- Wrong input type (string instead of number, and so on)
- Missing required fields
- Invalid values (negative where positive is expected, and so on)
- Missing or unreachable dependencies
- Timeouts (for async operations)
- Correct error messages and error codes

### State-dependent tests

- Initial state (before the first call)
- After mutation (after add, change, delete)
- Concurrent access (where relevant)
- Idempotence (same call, same result)

### Integration-specific

- Correct hand-over between modules
- Data transformation at module boundaries
- Error propagation through the chain
- Correct order of operations

### Coverage strategy

Not every function needs every check. Prioritize:

1. **Critical path:** always test completely
2. **Error handling:** always test (often the most important tests)
3. **Edge cases:** for functions with complex logic
4. **Trivial getters and setters:** do not test (unless they hold logic)
