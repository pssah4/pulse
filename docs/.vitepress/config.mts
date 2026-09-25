import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

const tutorialsSidebar = [
  {
    text: 'Tutorials',
    items: [
      { text: 'Installation', link: '/tutorials/installation' },
      { text: 'Your first business analysis', link: '/tutorials/first-business-analysis' },
      { text: 'A full V-Model run', link: '/tutorials/full-v-model-run' },
    ],
  },
]

const guidesSidebar = [
  {
    text: 'Start',
    items: [
      { text: '/pulse', link: '/guides/pulse' },
      { text: '/pulse-setup', link: '/guides/pulse-setup' },
      { text: '/pulse-realign', link: '/guides/pulse-realign' },
    ],
  },
  {
    text: 'Digital Innovation Agents',
    items: [
      { text: '/pulse-ba', link: '/guides/pulse-ba' },
      { text: '/pulse-re', link: '/guides/pulse-re' },
      { text: 'Planning', link: '/guides/pulse-plan' },
      { text: '/pulse-build', link: '/guides/pulse-build' },
      { text: 'Review', link: '/guides/pulse-review' },
      { text: '/pulse-audit', link: '/guides/pulse-audit' },
    ],
  },
  {
    text: 'Collaboration',
    items: [
      { text: '/pulse-go', link: '/guides/pulse-go' },
      { text: '/pulse-map', link: '/guides/pulse-map' },
    ],
  },
]

const referenceSidebar = [
  {
    text: 'Reference',
    items: [
      { text: 'Commands', link: '/reference/commands' },
      { text: 'Configuration', link: '/reference/configuration' },
      { text: 'Artifacts', link: '/reference/artifacts' },
      { text: 'Reachability by stack', link: '/reference/reachability-by-stack' },
      { text: 'Troubleshooting', link: '/reference/troubleshooting' },
    ],
  },
  {
    text: 'Methods (BA and RE toolkit)',
    items: [
      { text: 'Discovery methods', link: '/reference/methods-discovery' },
      { text: 'Ideation methods', link: '/reference/methods-ideation' },
      { text: 'Validation methods', link: '/reference/methods-validation' },
    ],
  },
]

const conceptsSidebar = [
  {
    text: 'Pulse',
    items: [
      { text: 'Operating model', link: '/operating-model' },
      { text: 'Parallel work', link: '/concepts/parallel-work' },
      { text: 'Where things live', link: '/concepts/where-things-live' },
    ],
  },
  {
    text: 'Digital Innovation Agents',
    items: [
      { text: 'The V-Model', link: '/concepts/v-model' },
      { text: 'Tech-agnostic requirements', link: '/concepts/tech-agnostic-requirements' },
      { text: 'Verification gates', link: '/concepts/verification-gates' },
    ],
  },
]

export default withMermaid(
  defineConfig({
    title: 'Pulse',
    description: 'Operating model, live collaboration, and the Digital Innovation Agents: from raw idea to shipped code, built in parallel by people and agents.',
    base: '/pulse/',
    head: [
      ['link', { rel: 'icon', type: 'image/svg+xml', href: '/pulse/assets/pulse-icon-hell.svg' }],
      ['meta', { name: 'theme-color', content: '#007780' }],
      ['meta', { property: 'og:title', content: 'Pulse' }],
      ['meta', { property: 'og:description', content: 'Operating model, live collaboration, and a V-Model method for teams of people and coding agents.' }],
      ['meta', { name: 'keywords', content: 'Pulse, V-Model, innovation, business analysis, requirements engineering, parallel agents, GitHub issues, ADR, OWASP, Claude Code, Cursor, Codex' }],
    ],

    appearance: { initialValue: 'light' },
    lastUpdated: true,
    cleanUrls: true,
    lang: 'en',

    themeConfig: {
      logo: { light: '/assets/pulse-logo-petrol.svg', dark: '/assets/pulse-logo-aqua.svg', alt: 'Pulse' },
      siteTitle: false,
      nav: [
        { text: 'Tutorials', link: '/tutorials/installation', activeMatch: '/tutorials/' },
        { text: 'Guides', link: '/guides/pulse', activeMatch: '/guides/' },
        { text: 'Concepts', link: '/operating-model', activeMatch: '/(concepts/|operating-model)' },
        { text: 'Reference', link: '/reference/commands', activeMatch: '/reference/' },
        { text: 'About', link: '/about' },
      ],
      sidebar: {
        '/tutorials/': tutorialsSidebar,
        '/guides/': guidesSidebar,
        '/reference/': referenceSidebar,
        '/concepts/': conceptsSidebar,
        '/operating-model': conceptsSidebar,
      },
      socialLinks: [
        { icon: 'github', link: 'https://github.com/pssah4/pulse' },
      ],
      search: {
        provider: 'local',
      },
      editLink: {
        pattern: 'https://github.com/pssah4/pulse/edit/main/docs/:path',
        text: 'Edit this page on GitHub',
      },
      footer: {
        message: '<a href="https://github.com/pssah4/pulse/blob/main/LICENSE">MIT License</a> | <a href="/pulse/imprint">Imprint</a>',
        copyright: 'Provided as-is, without any warranty or liability.',
      },
    },

    mermaid: {},
  }),
)
