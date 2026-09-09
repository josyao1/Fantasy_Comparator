#!/usr/bin/env bash
# Pushes local .env values into GitHub Actions secrets and variables.
# Values are read from .env and piped straight to gh — never printed.
set -euo pipefail
cd "$(dirname "$0")"

REPO="josyao1/Fantasy_Comparator"
[ -f .env ] || { echo "no .env here"; exit 1; }

get() { grep -m1 "^$1=" .env | cut -d= -f2- ; }

# Secrets sourced from .env
for K in SLEEPER_USER_ID SLEEPER_LEAGUES ESPN_LEAGUES ESPN_S2 SWID \
         GMAIL_USER GMAIL_APP_PW SMS_TO; do
  V="$(get "$K")"
  if [ -z "$V" ]; then echo "  skip   $K (empty in .env)"; continue; fi
  printf '%s' "$V" | gh secret set "$K" --repo "$REPO" >/dev/null
  echo "  secret $K"
done

# Vercel deploy credentials
if [ -f .vercel/project.json ]; then
  ORG=$(python3 -c "import json;print(json.load(open('.vercel/project.json'))['orgId'])")
  PRJ=$(python3 -c "import json;print(json.load(open('.vercel/project.json'))['projectId'])")
  printf '%s' "$ORG" | gh secret set VERCEL_ORG_ID     --repo "$REPO" >/dev/null
  printf '%s' "$PRJ" | gh secret set VERCEL_PROJECT_ID --repo "$REPO" >/dev/null
  echo "  secret VERCEL_ORG_ID"
  echo "  secret VERCEL_PROJECT_ID"
fi

if [ -n "${VERCEL_TOKEN:-}" ]; then
  printf '%s' "$VERCEL_TOKEN" | gh secret set VERCEL_TOKEN --repo "$REPO" >/dev/null
  echo "  secret VERCEL_TOKEN"
else
  echo "  TODO   VERCEL_TOKEN — create at https://vercel.com/account/tokens, then:"
  echo "         VERCEL_TOKEN=xxx ./setup_actions.sh"
fi

# Non-secret variables
gh variable set BOARD_BASE_URL --repo "$REPO" --body "$(get BOARD_BASE_URL)" >/dev/null
gh variable set SEND_MODE      --repo "$REPO" --body "daily" >/dev/null
gh variable set LEAD_MINUTES   --repo "$REPO" --body "90" >/dev/null
echo "  vars   BOARD_BASE_URL, SEND_MODE, LEAD_MINUTES"

echo
echo "done. verify with:  gh secret list --repo $REPO"
