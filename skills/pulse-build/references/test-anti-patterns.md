# Test anti-patterns

## 1. Testing implementation details

```
WRONG: test that Array.sort() is called internally
RIGHT: test that the result is sorted

WRONG: test that a private method is called
RIGHT: test the public behavior that results from it
```

Why: tests coupled to the implementation break on every refactor.

## 2. Excessive mocking

```
WRONG: 5+ mocks for a single test
RIGHT: at most 2 to 3 mocks, the rest through dependency injection

WRONG: mocking the unit under test
RIGHT: mock external dependencies only
```

Why: too many mocks test the mock code, not the logic. A test that needs
many mocks points at a design problem in the code.

## 3. Trivial tests

```
WRONG:
  it('should return true', () => {
    expect(true).toBe(true);
  });

WRONG:
  it('should set name', () => {
    user.name = 'Max';
    expect(user.name).toBe('Max');
  });

RIGHT: test only logic that can go wrong
```

## 4. Fragile tests

```
WRONG: assert the exact error message string
  expect(error.message).toBe('User with ID 42 not found in database schema "public"');

RIGHT: assert the relevant part
  expect(error.message).toContain('not found');
  expect(error.code).toBe('USER_NOT_FOUND');
```

## 5. Dependent tests

```
WRONG: test B needs the result of test A
RIGHT: every test has its own setup and runs on its own
```

## 6. Non-deterministic tests

```
WRONG: tests using Date.now() or Math.random()
RIGHT: inject the clock and the random source, or pin the values
```

## 7. God tests

```
WRONG: one test with 20 assertions
RIGHT: one test, one behavior, a few related assertions
```

## 8. Copy-paste tests without variation

```
WRONG: 10 tests that differ only in their input
RIGHT: parameterized tests (test.each / @pytest.mark.parametrize)
```

## 9. Tests that only drive coverage

```
WRONG: a test that calls a function but asserts nothing
RIGHT: every test has at least one meaningful assertion
```

## 10. Sleep or delay in tests

```
WRONG: await sleep(1000); expect(result).toBe(true);
RIGHT: use waitFor, polling, or events instead of fixed waits
```
