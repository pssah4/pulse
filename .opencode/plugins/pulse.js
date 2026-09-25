/**
 * Pulse plugin for OpenCode.ai
 *
 * Injects the Pulse rules into the first message of each session.
 * Auto-registers skills directory via config hook (no symlinks needed).
 *
 * Adapted from superpowers plugin:
 * https://github.com/obra/superpowers/blob/main/.opencode/plugins/superpowers.js
 */

import path from 'path';
import fs from 'fs';
import os from 'os';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const normalizePath = (p, homeDir) => {
  if (!p || typeof p !== 'string') return null;
  let normalized = p.trim();
  if (!normalized) return null;
  if (normalized.startsWith('~/')) {
    normalized = path.join(homeDir, normalized.slice(2));
  } else if (normalized === '~') {
    normalized = homeDir;
  }
  return path.resolve(normalized);
};

export const PulsePlugin = async ({ client, directory }) => {
  const homeDir = os.homedir();
  const pluginRoot = path.resolve(__dirname, '../..');
  const skillsDir = path.resolve(pluginRoot, 'skills');
  const envConfigDir = normalizePath(process.env.OPENCODE_CONFIG_DIR, homeDir);
  const configDir = envConfigDir || path.join(homeDir, '.config/opencode');

  // The project's mode: .pulse/config.toml first, then the settings file
  // of the predecessor plugin (.dia/config.toml). Walks up from the
  // session directory; a project with neither counts as on.
  const readMode = () => {
    let dir = directory ? path.resolve(directory) : process.cwd();
    while (true) {
      for (const [name, off] of [['.pulse', /^[ \t]*mode\s*=\s*["']off["']/m],
                                 ['.dia', /^[ \t]*mode\s*=\s*["']off["']/m]]) {
        const file = path.join(dir, name, 'config.toml');
        try {
          if (fs.existsSync(file)) return off.test(fs.readFileSync(file, 'utf8')) ? 'off' : 'on';
        } catch {
          // unreadable: keep walking
        }
      }
      const parent = path.dirname(dir);
      if (parent === dir) return 'on';
      dir = parent;
    }
  };

  const mode = readMode();

  // Helper to generate bootstrap content
  const getBootstrapContent = () => {
    const rulesPath = path.join(pluginRoot, 'hooks', 'rules.md');
    if (!fs.existsSync(rulesPath)) return null;

    const content = fs.readFileSync(rulesPath, 'utf8');
    const cli = path.join(pluginRoot, 'bin', 'pulse');

    const toolMapping = `**Tool Mapping for OpenCode:**
When skills reference tools you don't have, substitute OpenCode equivalents:
- \`TodoWrite\` -> \`todowrite\`
- \`Task\` tool with subagents -> Use OpenCode's subagent system (@mention)
- \`Skill\` tool -> OpenCode's native \`skill\` tool
- \`Read\`, \`Write\`, \`Edit\`, \`Bash\` -> Your native tools

Use OpenCode's native \`skill\` tool to list and load skills.`;

    return `<EXTREMELY_IMPORTANT>
You have Pulse skills. The Pulse rules below are already loaded.

${content}

Pulse CLI: \`${cli}\`. Wherever these rules or a Pulse skill say \`pulse\`, run that path.

${toolMapping}
</EXTREMELY_IMPORTANT>`;
  };

  return {
    // Inject skills path into live config so OpenCode discovers the skills
    // without requiring manual symlinks or config file edits. Skipped
    // when the project opts out via mode = "off" so the plugin really
    // disappears for that project.
    config: async (config) => {
      if (mode === 'off') return;
      config.skills = config.skills || {};
      config.skills.paths = config.skills.paths || [];
      if (!config.skills.paths.includes(skillsDir)) {
        config.skills.paths.push(skillsDir);
      }
    },

    // Inject bootstrap into the first user message of each session.
    // Using a user message instead of a system message avoids:
    //   1. Token bloat from system messages repeated every turn
    //   2. Multiple system messages breaking some models
    // Skipped when the project's mode is "off", like the Claude Code hooks.
    'experimental.chat.messages.transform': async (_input, output) => {
      if (mode === 'off') return;
      const bootstrap = getBootstrapContent();
      if (!bootstrap || !output.messages.length) return;
      const firstUser = output.messages.find(m => m.info.role === 'user');
      if (!firstUser || !firstUser.parts.length) return;
      // Only inject once
      if (firstUser.parts.some(p => p.type === 'text' && p.text.includes('EXTREMELY_IMPORTANT'))) return;
      const ref = firstUser.parts[0];
      firstUser.parts.unshift({ ...ref, type: 'text', text: bootstrap });
    }
  };
};
