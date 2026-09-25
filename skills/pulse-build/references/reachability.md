# Reachability and Activation Path

The done-contract of `/pulse-build`: a new symbol has a caller, and a
feature's Activation Path exists in the code. The contract is universal;
the tooling that checks it is per language. Each stack entry below
carries reachability tooling, the activation path types of that stack,
and the cleanup pattern to look for when listeners or resources appear.
The list grows by PR; for a missing stack, copy the closest entry.

## Reachability subtypes

For every new top-level symbol introduced in a session (class, function,
module, command, route, handler, tool registration), verify a caller
exists outside the definition file and outside test files.

- `subtype: user-facing` (default): caller MUST exist outside definition
  file and outside tests. A symbol that compiles but is never called
  fails the check.
- `subtype: library`: caller MUST exist OR the symbol is exported as a
  public API entry point and documented as such.

On fail, the feature may not close. Options:
1. Wire it up (add the caller).
2. Demote `subtype:` to `library` with public API documentation.
3. Leave a `FIXME(stub): wiring open -- see #<n>` at the definition,
   open that issue, and keep the feature open.

Stack-specific tooling for the scan follows below.

## Activation Path entry types

For every feature about to close, read the `## Activation Path` section
of its spec and verify each entry exists in the code (grep or AST
query). The string in the spec MUST match an actual identifier in the
code.

| Type            | Required proof                                            |
|-----------------|-----------------------------------------------------------|
| command         | command name registered in command registry              |
| route           | route path registered in router                          |
| UI-element      | element rendered in component tree or template           |
| endpoint        | handler registered with the framework                    |
| scheduled-job   | schedule registered with the scheduler                   |
| tool            | tool name registered in the agent tool registry          |
| hotkey          | hotkey registered with the platform                      |
| public-API      | symbol exported in the package's public surface          |

On fail, the feature may not close.

## Configuration

A project can name its stack and a custom check in `.pulse/config.toml`:

```toml
stack = "typescript-obsidian-plugin"
reachability_check = "scripts/check-reachability.sh"
```

With `stack` set, use the matching entry below. With
`reachability_check` set, run that script: exit 0 passes, anything else
fails, stdout explains. With neither, say "no reachability tooling
configured" and fall back to the universal layer, which always runs: the
Activation Path identifier appears in the source tree (plain grep).

---

## TypeScript / Node

**Reachability tooling:**

- `npx ts-prune` -- finds exported symbols never imported elsewhere.
- `npx tsc --noUnusedLocals --noUnusedParameters` -- compiler-level
  unused-symbol report.
- `npx ts-morph` programmatic find-references for spot checks.
- `grep -rn "import.*from.*['\"]<module-path>['\"]" src/` for a quick
  caller spot-check on a specific symbol.

**Activation path types:**

- `command` -- registered with the framework's command bus or CLI
  framework (yargs, commander, oclif).
- `route` -- HTTP route registered on Express, Fastify, Hono,
  NestJS controllers.
- `endpoint` -- the same as `route` for non-HTTP transports (RPC,
  WebSocket).
- `scheduled-job` -- node-cron, agenda, BullMQ.
- `tool` -- agent tool registered with the framework (LangChain
  tools, OpenAI function-calling tools).
- `public-API` -- exported from `index.ts` or named in the package's
  `exports` field in `package.json`.

**Cleanup pattern:**

- `process.on('exit', ...)` for top-level cleanup.
- `AbortController.signal.addEventListener('abort', ...)` for
  cancellable async work.
- Explicit `dispose()` / `close()` on sockets, file handles,
  timers (`clearTimeout` / `clearInterval`).

---

## TypeScript -- Obsidian Plugin sub-profile

A specialisation of the TypeScript entry. Adds plugin-specific
activation paths and the `onunload` cleanup contract.

**Reachability tooling:** same as TypeScript above. Plus:

- `grep -rn "new <ClassName>" src/` -- the specific failure mode in
  Obsidian plugins is "class file exists, never instantiated".
- `grep -rn "<className>:" src/` -- for tools registered as
  `{ name: 'className', ... }` in a registry.

**Activation path types:**

- `command` -- registered via `this.addCommand({ id, name, callback })`
  in `main.ts` `onload`.
- `tool` -- registered in `ToolRegistry` AND added to a `TOOL_GROUPS`
  entry in `ToolExecutionPipeline` (the dual registration is the
  Obsilo-pattern; both are mandatory).
- `UI-element` -- modal, side panel, status bar item, ribbon icon,
  rendered through `app.workspace`.
- `hotkey` -- registered as part of `addCommand` with a `hotkeys`
  array.
- `settings-toggle` -- option in the Settings tab; counts as an
  activation path because the user can flip it.
- `auto-trigger` -- `vault.on('event', ...)`, `MutationObserver`,
  `setInterval` -- listeners registered in `onload` or in a service
  initialised by `main.ts`.

**Cleanup pattern (mandatory in Obsidian plugins):**

- Every `vault.on(...)` MUST have a paired `vault.off(...)` in
  `onunload`.
- Every `register*` call (`registerEvent`, `registerInterval`,
  `registerDomEvent`) is auto-cleaned by the platform; prefer them
  over raw `.on` when possible.
- Every `setInterval` MUST have a `clearInterval` in `onunload`.
- Cleanup wrap in `try/catch` so one failing teardown does not block
  the rest.

---

## JavaScript (browser or Node, no TypeScript)

**Reachability tooling:**

- `npx eslint --rule 'no-unused-vars: error' --rule 'import/no-unused-modules: error'`.
- `npx depcheck` for unused dependencies (related signal: a new
  module was supposed to be the consumer of a dependency).
- `grep -rn "require.*<module>"` and `grep -rn "import.*from.*<module>"`.

**Activation path types:** same as TypeScript. Public-API for
libraries lives in `module.exports` (CommonJS) or named exports
(ESM).

**Cleanup pattern:** same as TypeScript.

---

## Python

**Reachability tooling:**

- `vulture src/` -- finds unused functions, classes, and imports.
  False positives on dynamic dispatch happen; whitelist via
  `vulture_whitelist.py`.
- `ruff check --select F401,F811,F841 src/` -- unused imports,
  redefinitions, unused locals.
- `python -c "import <module>; print([x for x in dir(<module>) if not x.startswith('_')])"`
  for quick public-symbol enumeration.
- AST walker (custom) for `find references to <symbol>` if the
  reference is dynamic (`getattr`, `__call__`, decorator-registered).

**Activation path types:**

- `command` -- argparse / click / typer subcommand registered in the
  CLI entry point.
- `route` -- FastAPI / Flask / Django route decorator on a function.
- `endpoint` -- gRPC service method registered on the server, Celery
  task name registered on the broker.
- `scheduled-job` -- APScheduler job, Celery beat schedule, Airflow
  DAG task.
- `tool` -- LangChain tool, OpenAI function-calling tool registered
  in the agent.
- `public-API` -- exported in `__init__.py` `__all__` list.

**Cleanup pattern:**

- Context managers (`with open(...)`, `__enter__`/`__exit__`).
- `try/finally` for guaranteed cleanup.
- `atexit.register(...)` for process-level cleanup.
- `weakref.finalize(...)` for object-level cleanup.

---

## Go

**Reachability tooling:**

- `staticcheck -checks=U1000 ./...` -- finds unused functions,
  variables, types.
- `gopls` `find-references` for editor-driven spot checks.
- `go vet ./...` -- catches unused imports and a few unused-symbol
  patterns.
- `unused -fields ./...` from `honnef.co/go/tools` for field-level
  analysis.

**Activation path types:**

- `command` -- cobra subcommand registered with `rootCmd.AddCommand(...)`.
- `route` -- HTTP handler registered on `http.ServeMux`, `chi`,
  `gin`, `echo`.
- `endpoint` -- gRPC service registered on the server.
- `scheduled-job` -- ticker-based goroutine started in `main` or a
  service constructor.
- `public-API` -- exported identifier (Capitalised name) in the
  package, documented at the package level.

**Cleanup pattern:**

- `defer` for function-scope cleanup.
- `context.WithCancel(...)` plus `<-ctx.Done()` plus `cancel()` for
  goroutine teardown.
- `signal.Notify(...)` for process-level shutdown.

---

## Rust

**Reachability tooling:**

- `cargo machete` -- unused dependencies.
- `cargo +nightly udeps` -- unused dependencies (more thorough).
- `cargo clippy -- -D dead_code` -- compiler dead-code lint as
  hard error.
- `rust-analyzer` `find references` for editor spot checks.
- `cargo doc` build does not fail on dead code but exposes orphans
  in the doc graph.

**Activation path types:**

- `command` -- clap subcommand registered with `#[derive(Subcommand)]`
  or `App::subcommand(...)`.
- `route` -- axum / actix / rocket route handler registered in the
  router.
- `endpoint` -- tonic gRPC service registered on the server.
- `scheduled-job` -- tokio-cron-scheduler job.
- `public-API` -- `pub` item in the crate root or in a re-export
  chain leading to the crate root, documented with `///`.

**Cleanup pattern:**

- `Drop` impl on types that hold resources (sockets, file handles,
  background tasks).
- Scope-end RAII for stack resources.
- `tokio::select!` with a cancellation branch for async tasks.

---

## React (TypeScript or JavaScript application)

**Reachability tooling:**

- `npx eslint-plugin-react/recommended` and
  `eslint-plugin-react-hooks/recommended` -- flag unused hooks and
  unmounted components.
- `npx ts-prune` (TypeScript projects) -- exported components never
  imported.
- `grep -rn "<ComponentName" src/` for JSX use spot check.
- `npx import-sort` and bundler analysers (webpack-bundle-analyzer,
  vite-bundle-visualizer) reveal which components ship in the
  bundle.

**Activation path types:**

- `route` -- registered with React Router (`<Route path="..." element={<Component />} />`),
  Next.js file-based routing, Remix loaders.
- `UI-element` -- component mounted in the application tree (find
  it in JSX of a parent that is itself reachable).
- `command` -- entry in a command palette component or
  context-menu registry.
- `endpoint` -- API route under `pages/api/` (Next.js) or
  `app/api/` (Next.js App Router) -- counts as an endpoint, not
  a route.
- `tool` -- registered with the framework's agent or AI SDK.
- `public-API` -- only relevant for component libraries; exported
  in `index.ts`.

**Cleanup pattern:**

- `useEffect(() => { ...; return () => { /* cleanup */ }; }, [...])`
  -- the return value is the cleanup function. Mandatory for
  subscriptions, intervals, and AbortController-based fetches.
- `AbortController.abort()` in the cleanup return for in-flight
  requests.
- `componentWillUnmount` for class components (legacy).

---

## R

**Reachability tooling:**

- `lintr::lint_package()` with `unused_import_linter()` and
  `object_usage_linter()`.
- `tools::checkUsagePackage(...)` -- CRAN-grade dead-code report.
- `grep -rn "<function-name>(" R/` for a caller spot check (R is
  permissive about dynamic dispatch; static analysis is partial).

**Activation path types:**

- `endpoint` -- plumber API route (`#* @get /path`).
- `UI-element` -- Shiny `output$<id>` paired with `<id>Output(...)`
  in the UI.
- `command` -- exported function in `NAMESPACE`, callable from a
  user script.
- `scheduled-job` -- cronR job, RStudio Connect scheduled report.
- `public-API` -- exported in `NAMESPACE` AND documented with
  `roxygen2` `@export`.

**Cleanup pattern:**

- `on.exit(...)` for function-scope cleanup.
- `withr::with_*` helpers for scoped state.
- Connection close: `close(con)` paired with `on.exit(close(con))`.

---

## Append rows

To add a new stack:

1. Pick the most similar existing entry as a template.
2. Fill the three sections (Reachability tooling, Activation path
   types, Cleanup pattern).
3. Open a PR titled `feat(build-ref): add reachability profile for
   <stack>`.
4. If your stack needs new activation-path types, add them to the
   feature template in `skills/pulse-re/templates/FEATURE-TEMPLATE.md`
   and to the Activation Path format in `skills/pulse-re/SKILL.md`.

Out of scope for now: smart-contract stacks (Solidity, Vyper),
mobile native (Swift, Kotlin), embedded (C, C++, Zig). These will be
added on demand when a DIA user works on a project of that class.
