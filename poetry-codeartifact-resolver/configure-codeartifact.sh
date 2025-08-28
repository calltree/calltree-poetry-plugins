#!/bin/bash

# Script to configure CodeArtifact authentication for poetry-codeartifact-resolver
# This sets up both environment variables (for CI/Docker) and Poetry config (like calltree auth)

set -e

# Configuration - Update these values or pass as environment variables
DOMAIN="${CODEARTIFACT_DOMAIN:-calltree}"
REPOSITORY="${CODEARTIFACT_REPOSITORY:-python-packages}"
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID="${CODEARTIFACT_ACCOUNT_ID:-831926607337}"
AWS_PROFILE="${AWS_PROFILE:-}"

# Function to run AWS CLI commands with optional profile
aws_cmd() {
    if [ -n "$AWS_PROFILE" ]; then
        aws --profile "$AWS_PROFILE" "$@"
    else
        aws "$@"
    fi
}

# Display configuration
echo "CodeArtifact Configuration:"
echo "  Domain: $DOMAIN"
echo "  Repository: $REPOSITORY"
echo "  Region: $REGION"
echo "  Account ID: $ACCOUNT_ID"
if [ -n "$AWS_PROFILE" ]; then
    echo "  AWS Profile: $AWS_PROFILE"
fi
echo ""

# Verify AWS credentials
echo "Verifying AWS credentials..."
if ! aws_cmd sts get-caller-identity > /dev/null 2>&1; then
    echo "Error: Unable to authenticate with AWS. Please check your credentials."
    exit 1
fi

# Get auth token
echo "Getting CodeArtifact authorization token..."
AUTH_TOKEN=$(aws_cmd codeartifact get-authorization-token \
    --domain $DOMAIN \
    --region $REGION \
    --query authorizationToken \
    --output text)

if [ -z "$AUTH_TOKEN" ]; then
    echo "Error: Failed to get authorization token"
    exit 1
fi

# Build repository URL
REPO_URL="https://${DOMAIN}-${ACCOUNT_ID}.d.codeartifact.${REGION}.amazonaws.com/pypi/${REPOSITORY}/"

echo "Configuring Poetry repository..."
poetry config repositories.codeartifact "$REPO_URL"
poetry config http-basic.codeartifact aws "$AUTH_TOKEN"

# Export environment variables (for CI/Docker compatibility)
echo "Exporting environment variables..."
export CODEARTIFACT_AUTH_TOKEN="$AUTH_TOKEN"
export AWS_REGION="$REGION"
export CODEARTIFACT_DOMAIN="$DOMAIN"
export CODEARTIFACT_REPOSITORY="$REPOSITORY"
export CODEARTIFACT_ACCOUNT_ID="$ACCOUNT_ID"

echo ""
echo "Configuration complete!"
echo ""
echo "For current session (CI/Docker):"
echo "  export CODEARTIFACT_AUTH_TOKEN='$AUTH_TOKEN'"
echo "  export AWS_REGION='$REGION'"
echo ""
echo "Poetry has also been configured directly for local development."
echo "The poetry-codeartifact-resolver plugin will work with either method."