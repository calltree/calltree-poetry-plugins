#!/bin/bash

# Script to publish poetry-local-resolver to AWS CodeArtifact

set -e

# Configuration - Update these values or pass as environment variables
DOMAIN="${CODEARTIFACT_DOMAIN:-your-domain}"
REPOSITORY="${CODEARTIFACT_REPOSITORY:-your-repository}"
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID="${CODEARTIFACT_ACCOUNT_ID:-your-account-id}"
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

echo "Configuring CodeArtifact authentication..."
aws_cmd codeartifact login --tool twine \
    --domain $DOMAIN \
    --repository $REPOSITORY \
    --region $REGION \
    --domain-owner $ACCOUNT_ID

# Get repository URL
REPO_URL=$(aws_cmd codeartifact get-repository-endpoint \
    --domain $DOMAIN \
    --repository $REPOSITORY \
    --format pypi \
    --region $REGION \
    --query repositoryEndpoint \
    --output text)

echo "Repository URL: $REPO_URL"

# Configure Poetry repository
poetry config repositories.codeartifact $REPO_URL

# Get auth token
AUTH_TOKEN=$(aws_cmd codeartifact get-authorization-token \
    --domain $DOMAIN \
    --region $REGION \
    --query authorizationToken \
    --output text)

poetry config http-basic.codeartifact aws $AUTH_TOKEN

echo "Publishing to CodeArtifact..."
poetry publish --repository codeartifact

echo "Package published successfully!"
echo ""
echo "To install in other projects:"
echo "  poetry self add poetry-local-resolver --source codeartifact"
echo ""
echo "Or with a specific AWS profile:"
echo "  AWS_PROFILE=$AWS_PROFILE poetry self add poetry-local-resolver --source codeartifact"