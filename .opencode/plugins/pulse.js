/**
 * Pulse plugin for OpenCode V2.
 *
 * Registers Pulse's skills and adds its rules to each agent-loop request.
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const pluginRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const skillsDir = path.join(pluginRoot, 'skills');

const readMode = (directory) => {
  let dir = path.resolve(directory || process.cwd());
  while (true) {
    for (const [name, off] of [['.pulse', /^[ \t]*mode\s*=\s*["']off["']/m],
                               ['.dia', /^[ \t]*mode\s*=\s*["']off["']/m]]) {
      const file = path.join(dir, name, 'config.toml');
      try {
        if (fs.existsSync(file)) return off.test(fs.readFileSync(file, 'utf8')) ? 'off' : 'on';
      } catch {
        // An unreadable config does not stop discovery in an ancestor.
      }
    }
    const parent = path.dirname(dir);
    if (parent === dir) return 'on';
    dir = parent;
  }
};

const frontmatterValue = (frontmatter, key) => {
  const lines = frontmatter.split(/\r?\n/);
  const first = lines.findIndex((line) => line.startsWith(`${key}:`));
  if (first < 0) return '';
  const value = lines[first].slice(key.length + 1).trim();
  if (value !== '>' && value !== '|') return value.replace(/^['"]|['"]$/g, '');

  const folded = [];
  for (const line of lines.slice(first + 1)) {
    if (!/^\s+/.test(line)) break;
    folded.push(line.trim());
  }
  return folded.join(value === '>' ? ' ' : '\n').trim();
};

const loadSkills = () => fs.readdirSync(skillsDir, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .flatMap((entry) => {
    const location = path.join(skillsDir, entry.name, 'SKILL.md');
    if (!fs.existsSync(location)) return [];
    const source = fs.readFileSync(location, 'utf8');
    const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
    const frontmatter = match?.[1] || '';
    return [{
      id: entry.name,
      name: frontmatterValue(frontmatter, 'name') || entry.name,
      description: frontmatterValue(frontmatter, 'description'),
      path: location,
      content: match ? source.slice(match[0].length) : source,
    }];
  });

const bootstrap = () => {
  const rulesPath = path.join(pluginRoot, 'hooks', 'rules.md');
  if (!fs.existsSync(rulesPath)) return null;
  const rules = fs.readFileSync(rulesPath, 'utf8');
  const cli = path.join(pluginRoot, 'bin', 'pulse');

  return `<EXTREMELY_IMPORTANT>
You have Pulse skills. The Pulse rules below are already loaded.

${rules}

Pulse CLI: \`${cli}\`. Wherever these rules or a Pulse skill say \`pulse\`, run that path.

**Tool Mapping for OpenCode:**
When skills reference tools you don't have, substitute OpenCode equivalents:
- \`TodoWrite\` -> your native todo tool
- \`Task\` tool with subagents -> OpenCode's subagent system
- \`Skill\` tool -> OpenCode's native \`skill\` tool
- \`Read\`, \`Write\`, \`Edit\`, \`Bash\` -> your native tools

Use OpenCode's native \`skill\` tool to list and load skills.
</EXTREMELY_IMPORTANT>`;
};

export default {
  id: 'pulse',
  async setup(ctx) {
    if (readMode(ctx.location.directory) === 'off') return;

    const skills = loadSkills();
    await ctx.skill.transform((editor) => {
      for (const skill of skills) editor.add(skill);
    });

    await ctx.command.transform((editor) => {
      for (const skill of skills) {
        editor.add({
          name: skill.id,
          description: skill.description,
          async execute({ sessionID, prompt, delivery }) {
            const selected = (prompt.skills || []).filter(({ id }) => id !== skill.id);
            await ctx.session.prompt({
              ...prompt,
              sessionID,
              skills: [...selected, { id: skill.id }],
              delivery,
            });
          },
        });
      }
    });

    const content = bootstrap();
    if (content) {
      await ctx.session.hook('context', (event) => {
        event.system.push({ type: 'text', text: content });
      });
    }
  },
};
