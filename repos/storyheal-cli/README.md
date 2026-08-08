# StoryHeal CLI

Operational CLI and stdio MCP server for StoryHeal. It covers support operations plus the governed Storyblok healing loop.

```bash
npm ci
npm run build
storyheal auth login --server https://support.example.com/api --username admin --password '...'
storyheal ops storyblok-test
storyheal ops storyblok-provision
storyheal ops findings
storyheal ops proposals --status reviewing
storyheal ops approve PROPOSAL_UUID --reason "Evidence verified"
storyheal ops analytics
```

Configuration is stored in `~/.storyheal/config.json`. Environment overrides are `STORYHEAL_SERVER`, `STORYHEAL_TOKEN`, `STORYHEAL_OUTPUT`, and `STORYHEAL_DEBUG`.

Run `storyheal --help` for chat, conversation, visitor, agent, provider, knowledge, platform, staff, and audit operations. `storyheal mcp serve` exposes the supported command surface over stdio.
