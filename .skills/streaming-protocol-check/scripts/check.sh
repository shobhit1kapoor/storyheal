#!/usr/bin/env bash
# streaming-protocol-check: verify streaming protocol consistency
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null || git diff --name-only --cached)
if [ -z "$CHANGED_FILES" ]; then
  echo "✓ No changes detected"
  exit 0
fi

# Check for streaming-related changes
STREAM_FILES=$(echo "$CHANGED_FILES" | grep -iE '(streaming/|stream|sse|wukongim|json.?render|MixedStream)' || true)

if [ -z "$STREAM_FILES" ]; then
  echo "✓ No streaming-related changes detected"
  exit 0
fi

echo "Streaming-related changes detected:"
echo "$STREAM_FILES" | sed 's/^/  /'
echo ""

echo "## Files to check for consistency"
echo ""

# Producer side (storyheal-ai)
echo "### Producer: storyheal-ai"
echo "  Streaming output:"
find repos/storyheal-ai -path "*/streaming/*" -type f 2>/dev/null | sed 's/^/    /' || echo "    (no streaming dir)"
echo "  Chat service:"
find repos/storyheal-ai -name "chat_service.py" -type f 2>/dev/null | sed 's/^/    /' || true
echo ""

# API relay (storyheal-api)
echo "### Relay: storyheal-api"
find repos/storyheal-api -name "*chat*" -o -name "*stream*" 2>/dev/null | grep -v __pycache__ | grep -v node_modules | sed 's/^/    /' || true
echo ""

# Consumer: storyheal-web
echo "### Consumer: storyheal-web"
echo "  Chat components:"
find repos/storyheal-web/src -path "*/chat/*" -type f 2>/dev/null | head -10 | sed 's/^/    /' || true
echo "  json-render:"
find repos/storyheal-web/src -path "*/jsonRender/*" -type f 2>/dev/null | sed 's/^/    /' || true
echo "  Stores:"
find repos/storyheal-web/src -name "*chatStore*" -o -name "*messageStore*" 2>/dev/null | sed 's/^/    /' || true
echo ""

# Consumer: storyheal-widget
echo "### Consumer: storyheal-widget"
echo "  Chat store:"
find repos/storyheal-widget/src -name "chatStore*" -type f 2>/dev/null | sed 's/^/    /' || true
echo "  json-render:"
find repos/storyheal-widget/src -path "*/jsonRender/*" -type f 2>/dev/null | sed 's/^/    /' || true
echo "  Messages:"
find repos/storyheal-widget/src -path "*/messages/*" -type f 2>/dev/null | sed 's/^/    /' || true
echo ""

# Consumer: storyheal-widget
echo "### Consumer: storyheal-widget"
echo "  Chat store:"
find repos/storyheal-widget/src -name "chatStore*" -type f 2>/dev/null | sed 's/^/    /' || true
echo "  json-render:"
find repos/storyheal-widget/src -path "*/json-render*" -type f 2>/dev/null | sed 's/^/    /' || true
echo ""

echo "## Protocol Contract (do not break)"
echo "  - SSE chunk format: data: {json}\\n\\n"
echo "  - Stream events: stream.delta, stream.close, stream.error"
echo "  - json-render: \`\`\`spec fence → JSONL patches"
echo "  - MixedStreamParser input/output must be consistent across all consumers"
