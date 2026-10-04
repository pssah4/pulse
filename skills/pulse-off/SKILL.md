---
name: pulse-off
description: >
  Turns Pulse off for the person in this clone, or with --host on this
  computer, without changing the team's configuration. Use only when the
  person types /pulse-off (in Codex $pulse:pulse-off).
argument-hint: "[--host]"
disable-model-invocation: true
---

# Turn Pulse off for yourself

The person's words after the command: `$ARGUMENTS`. In Codex they are the
words after `$pulse:pulse-off` in the person's message. With `--host`, or
words such as "everywhere" or "this computer", the switch is the one for
every project on this computer; otherwise it is the one for this clone.

Off means: no rules, no guard and no presence in this person's sessions
here, and `pulse go` does not start. Nothing in the repository changes, and
the team's mode stays as it is.

In Claude Code, run `pulse off` (or `pulse off --host`) as one plain command
on its own, nothing before or after it, with Pulse's own `pulse`: Claude
Code puts the plugin's `bin/` on the PATH of its Bash tool, and where it is
not there (the rules name the path while Pulse is on, but not while it is
off), use the `bin/pulse` two folders above this skill's own folder. Claude
Code then asks the person in its own dialog; only their answer switches
Pulse, and the hook reports the new state once the command is done. Report
that note, which switch is off and how `/pulse-on` turns it on again.
Without the note, Pulse did not switch: say so and give the command's own
output.

In Codex there is no dialog the model cannot answer, and the Codex rules
forbid `pulse on` and `pulse off` to the agent: run nothing. Hand the
person the command for their own terminal: `pulse off`, or
`pulse off --host` for every project on this computer. `pulse` there is the
command `pulse setup --cli` puts into `~/.local/bin`; without it the person
runs `bin/pulse` of this Pulse copy, two folders above this skill's own
folder, since with Pulse off the session has no rules that name the path.
