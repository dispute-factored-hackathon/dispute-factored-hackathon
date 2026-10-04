#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
AWS_REGION="${AWS_REGION:-sa-east-1}"
PROJECT_NAME="${PROJECT_NAME:-dispute-factored}"
BOOTSTRAP_STACK="${PROJECT_NAME}-bootstrap"
APPLICATION_STACK="${PROJECT_NAME}-demo"
DATABASE_STACK="${PROJECT_NAME}-database"
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo local)"
IMAGE_TAG="${IMAGE_TAG:-${GIT_SHA}-$(date +%Y%m%d%H%M%S)}"
LANGSMITH_SECRET_ID="${LANGSMITH_SECRET_ID:-${PROJECT_NAME}/langsmith}"
LANGSMITH_PROJECT="${LANGSMITH_PROJECT:-${PROJECT_NAME}}"
HUMAN_HANDOFF_NUMBER="${HUMAN_HANDOFF_NUMBER:-+5511981020050}"
VOICE_SNAPSTART_APPLY_ON="${VOICE_SNAPSTART_APPLY_ON:-PublishedVersions}"

stack_output() {
  aws cloudformation describe-stacks \
    --region "${AWS_REGION}" \
    --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" \
    --output text
}

deploy_database() {
  aws cloudformation deploy \
    --region "${AWS_REGION}" \
    --stack-name "${DATABASE_STACK}" \
    --template-file infra/aws/database.yaml \
    --parameter-overrides ProjectName="${PROJECT_NAME}"

  MOTHERDUCK_SECRET_ARN="$(stack_output "${DATABASE_STACK}" MotherDuckSecretArn)"
  uv run python infra/aws/sync_runtime_secrets.py \
    --region "${AWS_REGION}" \
    --motherduck-secret-arn "${MOTHERDUCK_SECRET_ARN}"
  echo "Database: $(stack_output "${DATABASE_STACK}" DatabaseHost)"
}

if [[ "${ACTION}" == "bootstrap" ]]; then
  aws cloudformation deploy \
    --region "${AWS_REGION}" \
    --stack-name "${BOOTSTRAP_STACK}" \
    --template-file infra/aws/bootstrap.yaml \
    --parameter-overrides ProjectName="${PROJECT_NAME}"
  echo "Repository: $(stack_output "${BOOTSTRAP_STACK}" RepositoryUri)"
  echo "Secret ARN: $(stack_output "${BOOTSTRAP_STACK}" OpenAISecretArn)"
  echo "Update that secret before deploying the application."
elif [[ "${ACTION}" == "database" ]]; then
  deploy_database
elif [[ "${ACTION}" == "application" || "${ACTION}" == "all" ]]; then
  if ! aws cloudformation describe-stacks \
    --region "${AWS_REGION}" --stack-name "${DATABASE_STACK}" >/dev/null 2>&1; then
    deploy_database
  fi
  REPOSITORY_URI="$(stack_output "${BOOTSTRAP_STACK}" RepositoryUri)"
  OPENAI_SECRET_ARN="$(stack_output "${BOOTSTRAP_STACK}" OpenAISecretArn)"

  if [[ -z "${REPOSITORY_URI}" || "${REPOSITORY_URI}" == "None" ]]; then
    echo "Bootstrap stack did not return RepositoryUri." >&2
    exit 1
  fi

  if [[ -z "${OPENAI_SECRET_ARN}" || "${OPENAI_SECRET_ARN}" == "None" ]]; then
    echo "Bootstrap stack did not return OpenAISecretArn." >&2
    exit 1
  fi

  LANGSMITH_SECRET_ARN="$(aws secretsmanager describe-secret \
    --region "${AWS_REGION}" \
    --secret-id "${LANGSMITH_SECRET_ID}" \
    --query ARN \
    --output text)"

  DATABASE_HOST="$(stack_output "${DATABASE_STACK}" DatabaseHost)"
  DATABASE_PORT="$(stack_output "${DATABASE_STACK}" DatabasePort)"
  DATABASE_NAME="$(stack_output "${DATABASE_STACK}" DatabaseName)"
  DATABASE_OWNER_SECRET_ARN="$(stack_output "${DATABASE_STACK}" DatabaseOwnerSecretArn)"
  DATABASE_APP_SECRET_ARN="$(stack_output "${DATABASE_STACK}" DatabaseAppSecretArn)"
  MOTHERDUCK_SECRET_ARN="$(stack_output "${DATABASE_STACK}" MotherDuckSecretArn)"
  uv run python infra/aws/sync_runtime_secrets.py \
    --region "${AWS_REGION}" \
    --motherduck-secret-arn "${MOTHERDUCK_SECRET_ARN}"

  if [[ -z "${LANGSMITH_SECRET_ARN}" || "${LANGSMITH_SECRET_ARN}" == "None" ]]; then
    echo "Unable to resolve LangSmith secret: ${LANGSMITH_SECRET_ID}" >&2
    exit 1
  fi

  REGISTRY="${REPOSITORY_URI%%/*}"
  IMAGE_URI="${REPOSITORY_URI}:${IMAGE_TAG}"
  DOCKER_DESKTOP_CONTEXT="$(docker context show)"
  DOCKER_HOST="$(docker context inspect "${DOCKER_DESKTOP_CONTEXT}" --format '{{.Endpoints.docker.Host}}')"
  export DOCKER_HOST
  DEPLOY_DOCKER_CONFIG="$(mktemp -d "${TMPDIR:-/tmp}/dispute-docker-config.XXXXXX")"
  export DOCKER_CONFIG="${DEPLOY_DOCKER_CONFIG}"
  cleanup() {
    if [[ "$(basename "${DEPLOY_DOCKER_CONFIG}")" == dispute-docker-config.* ]]; then
      rm -rf -- "${DEPLOY_DOCKER_CONFIG}"
    fi
  }
  trap cleanup EXIT

  aws ecr get-login-password --region "${AWS_REGION}" | \
    python3 infra/aws/write_docker_auth.py "${DOCKER_CONFIG}/config.json" "${REGISTRY}"

  docker buildx build \
    --platform linux/amd64 \
    --file Dockerfile.aws \
    --tag "${IMAGE_URI}" \
    --push .

  aws cloudformation deploy \
    --region "${AWS_REGION}" \
    --stack-name "${APPLICATION_STACK}" \
    --template-file infra/aws/application.yaml \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides \
      ProjectName="${PROJECT_NAME}" \
      ContainerImageUri="${IMAGE_URI}" \
      OpenAISecretArn="${OPENAI_SECRET_ARN}" \
      LangSmithSecretArn="${LANGSMITH_SECRET_ARN}" \
      DatabaseHost="${DATABASE_HOST}" \
      DatabasePort="${DATABASE_PORT}" \
      DatabaseName="${DATABASE_NAME}" \
      DatabaseOwnerSecretArn="${DATABASE_OWNER_SECRET_ARN}" \
      DatabaseAppSecretArn="${DATABASE_APP_SECRET_ARN}" \
      MotherDuckSecretArn="${MOTHERDUCK_SECRET_ARN}" \
      PrivateSubnetIds="$(stack_output "${DATABASE_STACK}" PrivateSubnetIds)" \
      LambdaSecurityGroupId="$(stack_output "${DATABASE_STACK}" LambdaSecurityGroupId)" \
      LangSmithProject="${LANGSMITH_PROJECT}" \
      HumanHandoffNumber="${HUMAN_HANDOFF_NUMBER}" \
      VoiceSnapStartApplyOn="${VOICE_SNAPSTART_APPLY_ON}"

  DATABASE_BOOTSTRAP_FUNCTION="$(stack_output "${APPLICATION_STACK}" DatabaseBootstrapFunctionName)"
  BOOTSTRAP_RESULT="$(mktemp "${TMPDIR:-/tmp}/dispute-db-bootstrap.XXXXXX")"
  aws --cli-read-timeout 900 lambda invoke \
    --region "${AWS_REGION}" \
    --function-name "${DATABASE_BOOTSTRAP_FUNCTION}" \
    --cli-binary-format raw-in-base64-out \
    --payload '{}' \
    "${BOOTSTRAP_RESULT}" >/dev/null
  if ! grep -q '"status"[[:space:]]*:[[:space:]]*"ready"' "${BOOTSTRAP_RESULT}"; then
    echo "Database bootstrap failed. Inspect /aws/lambda/${DATABASE_BOOTSTRAP_FUNCTION}." >&2
    rm -f -- "${BOOTSTRAP_RESULT}"
    exit 1
  fi
  rm -f -- "${BOOTSTRAP_RESULT}"

  SIP_FUNCTION_NAME="$(stack_output "${APPLICATION_STACK}" FunctionName)"
  SIP_PUBLISHED_VERSION="$(stack_output "${APPLICATION_STACK}" SipPublishedVersion)"
  SNAPSTART_STATUS="$(aws lambda get-function-configuration \
    --region "${AWS_REGION}" \
    --function-name "${SIP_FUNCTION_NAME}" \
    --qualifier "${SIP_PUBLISHED_VERSION}" \
    --query 'SnapStart.OptimizationStatus' \
    --output text)"

  if [[ "${VOICE_SNAPSTART_APPLY_ON}" == "PublishedVersions" && "${SNAPSTART_STATUS}" != "On" ]]; then
    echo "SnapStart is not ready for ${SIP_FUNCTION_NAME}:${SIP_PUBLISHED_VERSION}." >&2
    exit 1
  fi

  echo "Image: ${IMAGE_URI}"
  echo "LangSmith project: ${LANGSMITH_PROJECT}"
  echo "Human handoff: configured"
  echo "Voice SnapStart: ${SNAPSTART_STATUS} (version ${SIP_PUBLISHED_VERSION})"
  echo "Application: $(stack_output "${APPLICATION_STACK}" ApplicationUrl)"
  echo "Webhook: $(stack_output "${APPLICATION_STACK}" OpenAIWebhookUrl)"
else
  echo "Usage: $0 bootstrap|database|application|all" >&2
  exit 2
fi
