---
name: pulse-on
description: >
  Turns the person's switch of Pulse on again, for this clone or with --host
  on this computer. Use only when the person types /pulse-on (in Codex
  $pulse:pulse-on).
argument-hint: "[--host]"
disable-model-invocation: true
---

# Turn Pulse on again for yourself

The person's words after the command: `$ARGUMENTS`. In Codex they are the
words after `$pulse:pulse-on` in the person's message. With `--host`, or
words such as "everywhere" or "this computer", the switch is the one for
every project on this computer; otherwise it is the one for this clone.

Each level has its own switch, and any switch that is off keeps Pulse off:
the person's switch for this clone, the one for this computer, and the
team's mode in `.pulse/config.toml`, which only `pulse setup --mode on` and
a commit change.

In Claude Code, run `pulse on` (or `pulse on --host`) as one plain command
on its own, nothing before or after it, with Pulse's own `pulse`: Claude
Code puts the plugin's `bin/` on the PATH of its Bash tool, and where it is
not there (the rules name the path while Pulse is on, but not while it is
off), use the `bin/pulse` two folders above this skill's own folder. Claude
Code then asks the person in its own dialog; only their answer switches
Pulse, and the hook reports the new state once the command is done. Report
that note: Pulse is on, or which switch still keeps it off and how that one
turns on. Without the note, Pulse did not switch: say so and give the
command's own output.

In Codex there is no dialog the model cannot answer, and the Codex rules
forbid `pulse on` and `pulse off` to the agent: run nothing. Hand the
person the command for their own terminal: `pulse on`, or
`pulse on --host` for every project on this computer. `pulse` there is the
command `pulse setup --cli` puts into `~/.local/bin`; without it the person
runs `bin/pulse` of this Pulse copy, two folders above this skill's own
folder, since with Pulse off the session has no rules that name the path.
