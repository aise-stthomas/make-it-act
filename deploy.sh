#!/usr/bin/env bash
# Deploy P3 to your AWS Academy Learner Lab account: four functions, one HTTP API, the tables.
#
#   ./deploy.sh                                   build and deploy (create or update), print the URL
#   ./deploy.sh --crash-after-effect issue_refund the same, with the kill switch on in the worker
#   ./deploy.sh --worker-timeout 30               a shorter worker timeout (the optional kill)
#
# Assumes: the AWS CLI with a live Learner Lab session, us-east-1, the pre-created LabRole,
# your Gemini key in .env. Writes API_URL and LAB_TOKEN to .env. ./teardown.sh removes it all.
set -euo pipefail
cd "$(dirname "$0")"
export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
PREFIX="${TABLE_PREFIX:-p3-}"; API_NAME="${API_NAME:-p3-api}"
CRASH=""; WORKER_TIMEOUT=120
while [ $# -gt 0 ]; do
  case "$1" in
    --crash-after-effect) CRASH="$2"; shift 2 ;;
    --worker-timeout) WORKER_TIMEOUT="$2"; shift 2 ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
done

[ -f .env ] || { echo "no .env: cp .env.example .env and paste your Gemini key"; exit 1; }
set -a; . ./.env; set +a
: "${GEMINI_API_KEY:?GEMINI_API_KEY is not set in .env}"
if [ -z "${LAB_TOKEN:-}" ]; then
  LAB_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  printf '\nLAB_TOKEN=%s\n' "$LAB_TOKEN" >> .env
fi
ACCOUNT="$(aws sts get-caller-identity --query Account --output text 2>/dev/null)" \
  || { echo "aws sts get-caller-identity failed: start a Learner Lab session and paste fresh credentials"; exit 1; }
ROLE="arn:aws:iam::${ACCOUNT}:role/LabRole"

echo "tables..."
for t in refunds runs approvals recordings crashes; do
  aws dynamodb describe-table --table-name "${PREFIX}$t" >/dev/null 2>&1 || \
    aws dynamodb create-table --table-name "${PREFIX}$t" --billing-mode PAY_PER_REQUEST \
      --attribute-definitions AttributeName=id,AttributeType=S --key-schema AttributeName=id,KeyType=HASH >/dev/null
done

echo "the API..."
API_ID="$(aws apigatewayv2 get-apis --query "Items[?Name=='${API_NAME}'].ApiId | [0]" --output text)"
if [ -z "$API_ID" ] || [ "$API_ID" = "None" ]; then
  API_ID="$(aws apigatewayv2 create-api --name "$API_NAME" --protocol-type HTTP --query ApiId --output text)"
  aws apigatewayv2 create-stage --api-id "$API_ID" --stage-name '$default' --auto-deploy >/dev/null
fi
API_URL="https://${API_ID}.execute-api.us-east-1.amazonaws.com"
mkdir -p build

echo "building the package..."
rm -f build/p3.zip && zip -qr build/p3.zip src data/seed -x '*__pycache__*'

# The functions' settings, written to a file so that no value is ever echoed by the AWS CLI.
GEMINI_API_KEY="$GEMINI_API_KEY" LAB_TOKEN="$LAB_TOKEN" PREFIX="$PREFIX" API_URL="$API_URL" CRASH="$CRASH" python3 - <<'PY'
import json, os
v = {"GEMINI_API_KEY": os.environ["GEMINI_API_KEY"], "LAB_TOKEN": os.environ["LAB_TOKEN"], "STORE": "dynamodb",
     "TABLE_PREFIX": os.environ["PREFIX"], "ORDERS_URL": os.environ["API_URL"] + "/mcp/orders",
     "PAYMENTS_URL": os.environ["API_URL"] + "/mcp/payments", "WORKER_FUNCTION": "p3-worker"}
if os.environ.get("CRASH"):
    v["CRASH_AFTER_EFFECT"] = os.environ["CRASH"]
json.dump({"Variables": v}, open("build/env.json", "w"))
PY
ENV="file://build/env.json"
deploy_fn() {   # name handler timeout
  if aws lambda get-function --function-name "p3-$1" >/dev/null 2>&1; then
    aws lambda update-function-code --function-name "p3-$1" --zip-file fileb://build/p3.zip >/dev/null
    aws lambda wait function-updated --function-name "p3-$1"
    aws lambda update-function-configuration --function-name "p3-$1" --timeout "$3" --environment "$ENV" >/dev/null
  else
    aws lambda create-function --function-name "p3-$1" --runtime python3.12 --role "$ROLE" \
      --handler "src.function.handlers.$2" --zip-file fileb://build/p3.zip --timeout "$3" --memory-size 256 \
      --environment "$ENV" >/dev/null
  fi
  aws lambda wait function-updated --function-name "p3-$1"
}
echo "functions..."
deploy_fn orders orders 15
deploy_fn payments payments 15
deploy_fn api api 29
deploy_fn worker worker "$WORKER_TIMEOUT"

route() {   # function "METHOD /path"
  local arn="arn:aws:lambda:us-east-1:${ACCOUNT}:function:p3-$1"
  local integ
  integ="$(aws apigatewayv2 get-integrations --api-id "$API_ID" --query "Items[?IntegrationUri=='${arn}'].IntegrationId | [0]" --output text)"
  if [ -z "$integ" ] || [ "$integ" = "None" ]; then
    integ="$(aws apigatewayv2 create-integration --api-id "$API_ID" --integration-type AWS_PROXY \
      --integration-uri "$arn" --payload-format-version 2.0 --query IntegrationId --output text)"
    aws lambda add-permission --function-name "p3-$1" --statement-id "apigw-$1" --action lambda:InvokeFunction \
      --principal apigateway.amazonaws.com --source-arn "arn:aws:execute-api:us-east-1:${ACCOUNT}:${API_ID}/*" >/dev/null 2>&1 || true
  fi
  local exists
  exists="$(aws apigatewayv2 get-routes --api-id "$API_ID" --query "Items[?RouteKey=='$2'].RouteId | [0]" --output text)"
  if [ -z "$exists" ] || [ "$exists" = "None" ]; then
    aws apigatewayv2 create-route --api-id "$API_ID" --route-key "$2" --target "integrations/$integ" >/dev/null
  fi
}
echo "routes..."
route orders "POST /mcp/orders"
route payments "POST /mcp/payments"
for r in "POST /tickets" "GET /runs/{id}" "POST /runs/{id}/resume" "GET /approvals" "POST /approvals/{id}"; do
  route api "$r"
done

grep -q '^API_URL=' .env && sed -i.bak "s|^API_URL=.*|API_URL=${API_URL}|" .env && rm -f .env.bak || printf 'API_URL=%s\n' "$API_URL" >> .env
echo
echo "deployed: $API_URL"
[ -n "$CRASH" ] && echo "kill switch ON: the worker exits once per run after $CRASH"
echo "check your server:  uv run check_server.py \$API_URL/mcp/payments"
echo "run the suite:      uv run run_suite.py --url \$API_URL"
