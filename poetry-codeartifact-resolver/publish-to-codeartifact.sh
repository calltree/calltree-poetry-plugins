#!/bin/bash

# Script to publish poetry-codeartifact-resolver to AWS CodeArtifact

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

echo "Building package..."
poetry build

# Check if we have a valid token or Poetry config
if [ -z "$CODEARTIFACT_AUTH_TOKEN" ]; then
    echo "No CODEARTIFACT_AUTH_TOKEN found. Checking Poetry configuration..."
    if ! poetry config repositories.codeartifact > /dev/null 2>&1; then
        echo "Error: No CodeArtifact authentication found."
        echo "Please run 'calltree auth' first."
        exit 1
    fi
    echo "Using existing Poetry configuration from 'calltree auth'."
    USE_POETRY_CONFIG=true
else
    echo "Using CODEARTIFACT_AUTH_TOKEN from environment."
    USE_POETRY_CONFIG=false
fi

# Build the repository URL based on current region
REPO_URL="https://${DOMAIN}-${ACCOUNT_ID}.d.codeartifact.${REGION}.amazonaws.com/pypi/${REPOSITORY}/"

if [ "$USE_POETRY_CONFIG" = "true" ]; then
    echo "Using existing Poetry configuration."
    # Repository already configured by calltree auth
else
    echo "Configuring Poetry with environment token:"
    echo "  Repository URL: $REPO_URL"
    echo "  Token: ${CODEARTIFACT_AUTH_TOKEN:0:20}..."
    
    # Configure Poetry repository using existing token
    poetry config repositories.codeartifact $REPO_URL
    poetry config http-basic.codeartifact aws $CODEARTIFACT_AUTH_TOKEN
fi

echo "Publishing to CodeArtifact..."
poetry publish --repository codeartifact

echo "Package published successfully!"
echo ""
echo "To install globally:"
echo "  poetry self add poetry-codeartifact-resolver"
echo ""
echo "Or with a specific AWS profile:"
echo "  AWS_PROFILE=$AWS_PROFILE poetry self add poetry-codeartifact-resolver"