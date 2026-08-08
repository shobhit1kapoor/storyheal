# StoryHeal

StoryHeal is a production-oriented, self-healing AI support and knowledge platform built for HackerNoon’s Proof of Usefulness — Storyblok track. Storyblok is the canonical editorial infrastructure; StoryHeal closes the loop between real support failures and measurable content improvement.

```text
support conversation
  → PII-redacted evidence
  → gap / contradiction / staleness agents
  → evidence and quality gates
  → structured Storyblok draft in Reviewing
  → accountable human approval
  → Storyblok publication
  → signed webhook
  → published CDA content re-indexed in RAG
  → corrected, cited answers and paired evaluation
```

## Why Storyblok is indispensable

- FAQ, documentation, troubleshooting, policy, known issue, product, and release-note schemas are provisioned through the Management API.
- English and Spanish use Storyblok field-level `__i18n__` translations.
- AI can create drafts but cannot publish. The publisher credential is only used after an authorized human approves the latest live draft.
- Webhook jobs never index draft payloads. They re-fetch published content from the Content Delivery API, wait for embeddings, and deduplicate by story, locale, publication data, and content hash.
- The public help center, AI grounding, widget citations, and support workspace share the same published entries.

## Focused monorepo

| Service | Responsibility |
| --- | --- |
| `storyheal-api` | Auth/RBAC, conversations, Storyblok integration, review, audit, analytics, durable workers |
| `storyheal-ai` | Typed specialist agents and existing provider/runtime support |
| `storyheal-rag` | pgvector retrieval and idempotent Storyblok external-source indexing |
| `storyheal-platform` | Real multichannel intake |
| `storyheal-web` | Admin control room, review UI, integration wizard, CDA help center |
| `storyheal-widget` | Embeddable support widget with citations and usefulness feedback |
| `storyheal-cli` | Operator/service CLI |

Device control, the plugin marketplace/runtime, generic workflow editing, mobile/mini-program SDKs, and live dependencies on the foundation’s former vendor have been removed.

## Quick start

Requirements: Docker with Compose v2, 8 GB RAM minimum (16 GB recommended for local Qwen), and a public HTTPS URL for real Storyblok webhooks.

```bash
cp .env.example .env
# Replace every CHANGE_ME value.
docker compose --profile local-ai up -d --build
```

Open `http://localhost` (or `HTTP_PORT`) and complete setup. In **Settings → Storyblok**:

1. Enter the region, space ID, separate draft/publisher Management tokens, public Delivery token, webhook secret, RAG collection, locales, and public HTTPS webhook URL.
2. Test all credentials.
3. Provision the StoryHeal components, content folder, workflow mapping, and signed webhook.
4. Sync existing published entries.

Storyblok secrets are encrypted in the API database and are never returned to the browser. Do not put Management credentials in frontend environment variables.

## Real acceptance path

1. Send an outdated question through the real widget, then close the session with a required resolution outcome.
2. Follow the durable run in **Knowledge healing**. Findings below the configured gate stay in triage.
3. Open the generated Storyblok draft. It must be in Reviewing and absent from RAG.
4. Review the live diff, redacted evidence, typed agent outputs, citations, translation score, evidence score, and QC score.
5. Approve as a user with `knowledge:publish`; StoryHeal re-fetches and re-checks the draft before publishing.
6. Observe the signed webhook receipt, CDA fetch, locale embeddings, and Indexed status.
7. Ask the frozen question again in English and Spanish. Verify corrected text, clickable sources, and paired before/after results.

## Usefulness metrics

- **Response accuracy:** pass rate of frozen evaluation questions against human-approved expected facts and citations.
- **Resolution rate:** eligible sessions resolved without handoff or reopening within 24 hours.
- **Response time:** message receipt to first AI token.
- **Before/after:** the same frozen questions and model settings immediately before publication and after webhook indexing.

The dashboard also reports funnel counts, Storyblok operations/failures, indexing time, localization, visitor feedback, and append-only audit events. JSON/CSV evidence export is available from the analytics API.

## Security and operations

- Secrets use authenticated server-side encryption.
- Webhooks use HMAC-SHA1 `webhook-signature` verification and durable receipt deduplication.
- Conversation evidence is redacted before model use, encrypted, and purged after 30 days.
- Project scope is enforced across connections, findings, proposals, metrics, and audit records.
- Postgres, Redis, WuKongIM, uploads, and optional Ollama use persistent volumes.
- `make backup` creates a PostgreSQL custom-format backup; `make restore FILE=...` restores one.

For production TLS, place `fullchain.pem` and `privkey.pem` in `data/certs/`, then start the HTTPS override:

```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml --profile local-ai up -d --build
```

The override redirects HTTP, terminates TLS 1.2/1.3 in Nginx, forwards signed Storyblok webhooks, and preserves secure WuKongIM WebSocket upgrades. The base `docker-compose.yml` remains convenient for local HTTP development.

## Tests

```bash
make test
cd repos/storyheal-web && yarn type-check && yarn build
cd repos/storyheal-widget && yarn build
```

Live Storyblok tests are environment-gated so the normal suite never mutates a real space.

## License

New StoryHeal work is licensed under Apache License 2.0. Notices and licenses for inherited foundation code are retained under [`THIRD_PARTY_NOTICES/`](THIRD_PARTY_NOTICES/).
