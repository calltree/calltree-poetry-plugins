#!/usr/bin/env bash

# Simple publish wrapper:
#   ./publish.sh <aws-profile> <dev|prod>
# Publishes poetry-codeartifact-resolver to the correct CodeArtifact region
# using the specified AWS profile. No extra env vars required.

set -euo pipefail

if [ $# -ne 2 ]; then
  echo "Usage: $0 <aws-profile> <dev|prod>" >&2
  exit 2
fi

PROFILE="$1"
STAGE="$2"

case "${STAGE}" in
  dev)  REGION="us-east-1" ;;
  prod) REGION="us-west-2" ;;
  *) echo "Invalid stage: ${STAGE}. Use 'dev' or 'prod'." >&2; exit 2 ;;
esac

# Fixed Calltree settings
DOMAIN="calltree"
REPOSITORY="python-packages"
ACCOUNT_ID="831926607337"

aws_cmd() {
  aws --profile "${PROFILE}" "$@"
}

echo "Publishing poetry-codeartifact-resolver"
echo "  Profile : ${PROFILE}"
echo "  Stage   : ${STAGE} (${REGION})"
echo "  Domain  : ${DOMAIN}"
echo "  Repo    : ${REPOSITORY}"
echo "  Account : ${ACCOUNT_ID}"

echo "Verifying AWS credentials..."
aws_cmd sts get-caller-identity >/dev/null

echo "Building package..."
poetry build

echo "Resolving repository endpoint..."
REPO_URL=$(aws_cmd codeartifact get-repository-endpoint \
  --domain "${DOMAIN}" \
  --repository "${REPOSITORY}" \
  --format pypi \
  --region "${REGION}" \
  --query repositoryEndpoint \
  --output text)

if [ -z "${REPO_URL}" ] || [ "${REPO_URL}" = "None" ]; then
  echo "Error: Repository endpoint not found for ${DOMAIN}/${REPOSITORY} in ${REGION}." >&2
  echo "Ensure the repository exists in that region." >&2
  exit 1
fi
echo "Repository URL: ${REPO_URL}"

echo "Fetching CodeArtifact authorization token..."
AUTH_TOKEN=$(aws_cmd codeartifact get-authorization-token \
  --domain "${DOMAIN}" \
  --domain-owner "${ACCOUNT_ID}" \
  --region "${REGION}" \
  --query authorizationToken \
  --output text)

if [ -z "${AUTH_TOKEN}" ] || [ "${AUTH_TOKEN}" = "None" ]; then
  echo "Error: Failed to obtain CodeArtifact auth token." >&2
  exit 1
fi

echo "Configuring Poetry and publishing..."
poetry config repositories.codeartifact "${REPO_URL}"
poetry config http-basic.codeartifact aws "${AUTH_TOKEN}"
poetry publish --repository codeartifact -n

echo "✅ Published successfully to ${REGION}."
echo "Tip: Install plugin into Poetry runtime:"
echo "  AWS_PROFILE=${PROFILE} poetry self add poetry-codeartifact-resolver --source codeartifact"

