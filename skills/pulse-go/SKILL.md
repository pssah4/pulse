---
name: pulse-go
description: >
  Starts or steers pulse go from the chat with the person's whole text as
  its goal. Use only when the person types /pulse-go (in Codex
  $pulse:pulse-go).
argument-hint: "[goal] | pause | resume | stop | steer <direction>"
disable-model-invocation: true
---

# pulse go from the chat

The person's words after the command: `$ARGUMENTS`. In Codex they are the
words after `$pulse:pulse-go` in the person's message.

| Words | Command |
|---|---|
| none | `pulse go` |
| `pause`, `resume` or `stop`, alone | `pulse go --pause`, `pulse go --resume` or `pulse go --stop` |
| `steer` and a direction | `pulse go --steer='<direction>'` |
| any other text | `pulse go -- '<the whole text>'` |

Keep every word of the text, combined instructions included, and pass it
as one argument in single quotes, each `'` in it written as `'\''`, so the
shell expands nothing; `--` and `--steer=` keep a text that begins with `-`
from being read as an option. Never replace the text with `--item` or
`--epic`: item numbers such as `#580` in the text already bound the run, and
a flag only ever goes next to the text. A goal that only begins with `pause`,
`resume` or `stop`, such as "stop the flicker in the map", stays a goal.
For `steer` without a direction, ask the person for it.

Run the command and report as [Start pulse go](../pulse/SKILL.md#start-pulse-go)
in the `pulse` skill says; markers, sandbox, receipt, report, and who never
starts a runner are written there once. A receipt with status `running`
names the runner that already works: report it with its state and start
no second one.
