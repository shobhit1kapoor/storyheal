#!/usr/bin/env bash
# functional-verification: use storyheal-cli and storyheal-widget-cli to verify API changes at runtime
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

StoryHeal_CLI="node repos/storyheal-cli/dist/index.js"
WIDGET_CLI="node repos/storyheal-widget-cli/dist/index.js"

# --- Helpers ---

PASSED=0
FAILED=0
SKIPPED=0

run_check() {
  local label="$1"
  shift
  printf "  %-50s" "$label"
  if OUTPUT=$("$@" 2>&1); then
    echo "✓"
    PASSED=$((PASSED + 1))
  else
    echo "✗"
    echo "    $OUTPUT" | head -3
    FAILED=$((FAILED + 1))
  fi
}

skip_check() {
  local label="$1"
  local reason="$2"
  printf "  %-50s⊘ %s\n" "$label" "$reason"
  SKIPPED=$((SKIPPED + 1))
}

# --- Preflight ---

echo "=== Functional Verification ==="
echo ""

# Check CLI builds
StoryHeal_CLI_OK=true
WIDGET_CLI_OK=true

if [ ! -f "repos/storyheal-cli/dist/index.js" ]; then
  echo "⚠ storyheal-cli not built. Run: cd repos/storyheal-cli && npm run build"
  StoryHeal_CLI_OK=false
fi

if [ ! -f "repos/storyheal-widget-cli/dist/index.js" ]; then
  echo "⚠ storyheal-widget-cli not built. Run: cd repos/storyheal-widget-cli && npm run build"
  WIDGET_CLI_OK=false
fi

# Check CLI configs
StoryHeal_CONFIGURED=true
WIDGET_CONFIGURED=true

if [ ! -f "$HOME/.storyheal/config.json" ]; then
  echo "⚠ storyheal-cli not configured. Run: $StoryHeal_CLI auth login -u <user> -p <pass>"
  StoryHeal_CONFIGURED=false
fi

if [ ! -f "$HOME/.storyheal-widget/config.json" ]; then
  echo "⚠ storyheal-widget-cli not configured. Run: $WIDGET_CLI init --api-key <key> --server <url>"
  WIDGET_CONFIGURED=false
fi

# Check server reachability
StoryHeal_SERVER=$(node -e "try{console.log(JSON.parse(require('fs').readFileSync('$HOME/.storyheal/config.json','utf8')).server||'')}catch{console.log('')}" 2>/dev/null || echo "")
SERVER_UP=false

if [ -n "$StoryHeal_SERVER" ]; then
  if curl -sf "${StoryHeal_SERVER}/api/v1/health" >/dev/null 2>&1 || curl -sf "${StoryHeal_SERVER}/health" >/dev/null 2>&1; then
    SERVER_UP=true
    echo "✓ Server reachable at $StoryHeal_SERVER"
  else
    echo "⚠ Server not reachable at $StoryHeal_SERVER — start with: make dev-all"
  fi
fi

if [ "$StoryHeal_CLI_OK" = false ] && [ "$WIDGET_CLI_OK" = false ]; then
  echo "✗ No CLIs available. Build them first."
  exit 1
fi

if [ "$SERVER_UP" = false ]; then
  echo "✗ Server not running. Start services first."
  exit 1
fi

echo ""

# --- Determine what to verify ---

RUN_ALL=false
TARGET_SERVICE=""

if [ "${1:-}" = "--all" ]; then
  RUN_ALL=true
elif [ -n "${1:-}" ]; then
  TARGET_SERVICE="$1"
else
  # Auto-detect from git diff
  CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null || git diff --name-only --cached)
  TARGET_SERVICES=$(echo "$CHANGED_FILES" | grep '^repos/' | cut -d'/' -f2 | sort -u || true)
fi

should_verify() {
  local service="$1"
  if [ "$RUN_ALL" = true ]; then return 0; fi
  if [ -n "$TARGET_SERVICE" ]; then
    [ "$TARGET_SERVICE" = "$service" ] && return 0 || return 1
  fi
  echo "$TARGET_SERVICES" | grep -q "^${service}$" 2>/dev/null && return 0 || return 1
}

# --- Staff-side checks (storyheal-cli) ---

if [ "$StoryHeal_CLI_OK" = true ] && [ "$StoryHeal_CONFIGURED" = true ]; then

  # System / API gateway
  if should_verify "storyheal-api" || [ "$RUN_ALL" = true ]; then
    echo "▶ storyheal-api (staff-side)"
    run_check "system info" $StoryHeal_CLI system info -o json
    run_check "auth whoami" $StoryHeal_CLI auth whoami -o json
    run_check "conversation list" $StoryHeal_CLI conversation list --limit 1 -o json
    run_check "visitor list" $StoryHeal_CLI visitor list --limit 1 -o json
    run_check "staff list" $StoryHeal_CLI staff list --limit 1 -o json
    echo ""
  fi

  # AI service
  if should_verify "storyheal-ai" || [ "$RUN_ALL" = true ]; then
    echo "▶ storyheal-ai (staff-side)"
    run_check "agent list" $StoryHeal_CLI agent list --limit 1 -o json
    run_check "provider list" $StoryHeal_CLI provider list -o json
    run_check "chat team (e2e)" $StoryHeal_CLI chat team --message "respond with just: ok" -o json
    echo ""
  fi

  # RAG service
  if should_verify "storyheal-rag" || [ "$RUN_ALL" = true ]; then
    echo "▶ storyheal-rag (staff-side)"
    run_check "knowledge list" $StoryHeal_CLI knowledge list --limit 1 -o json
    echo ""
  fi

  # Workflow service
  if should_verify "storyheal-workflow" || [ "$RUN_ALL" = true ]; then
    echo "▶ storyheal-workflow (staff-side)"
    run_check "workflow list" $StoryHeal_CLI workflow list --limit 1 -o json
    echo ""
  fi

  # Platform service
  if should_verify "storyheal-platform" || [ "$RUN_ALL" = true ]; then
    echo "▶ storyheal-platform (staff-side)"
    run_check "platform list" $StoryHeal_CLI platform list -o json
    echo ""
  fi

else
  skip_check "staff-side checks" "storyheal-cli not available or not configured"
  echo ""
fi

# --- Visitor-side checks (storyheal-widget-cli) ---

if [ "$WIDGET_CLI_OK" = true ] && [ "$WIDGET_CONFIGURED" = true ]; then

  VISITOR_RELEVANT=false
  if should_verify "storyheal-api" || should_verify "storyheal-ai" || should_verify "storyheal-widget" || should_verify "storyheal-widget" || should_verify "storyheal-platform" || [ "$RUN_ALL" = true ]; then
    VISITOR_RELEVANT=true
  fi

  if [ "$VISITOR_RELEVANT" = true ]; then
    echo "▶ Visitor-side"
    run_check "platform info" $WIDGET_CLI platform info -o json
    run_check "channel info" $WIDGET_CLI channel info -o json
    run_check "chat history" $WIDGET_CLI chat history --limit 3 -o json
    run_check "chat send (e2e, no-stream)" $WIDGET_CLI chat send --message "respond with just: ok" --no-stream -o json
    echo ""
  fi

else
  if should_verify "storyheal-api" || should_verify "storyheal-widget" || [ "$RUN_ALL" = true ]; then
    skip_check "visitor-side checks" "storyheal-widget-cli not available or not configured"
    echo ""
  fi
fi

# --- Summary ---

echo "=== Summary ==="
TOTAL=$((PASSED + FAILED + SKIPPED))
echo "  Passed:  $PASSED"
echo "  Failed:  $FAILED"
echo "  Skipped: $SKIPPED"
echo "  Total:   $TOTAL"

if [ "$FAILED" -gt 0 ]; then
  echo ""
  echo "✗ Some checks FAILED"
  exit 1
else
  echo ""
  echo "✓ All checks passed"
fi
