#!/usr/bin/env bash
# Remove everything deploy.sh made: the API, the four functions, the tables (your data).
set -uo pipefail
cd "$(dirname "$0")"
export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
PREFIX="${TABLE_PREFIX:-p3-}"; API_NAME="${API_NAME:-p3-api}"
ID="$(aws apigatewayv2 get-apis --query "Items[?Name=='${API_NAME}'].ApiId | [0]" --output text 2>/dev/null)"
if [ -n "$ID" ] && [ "$ID" != "None" ]; then aws apigatewayv2 delete-api --api-id "$ID" && echo "deleted the API"; fi
for f in orders payments api worker; do
  aws lambda delete-function --function-name "p3-$f" 2>/dev/null && echo "deleted p3-$f"
done
for t in refunds runs approvals recordings crashes; do
  aws dynamodb delete-table --table-name "${PREFIX}$t" >/dev/null 2>&1 && echo "deleted the table ${PREFIX}$t"
done
