#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
AWS_REGION="${AWS_REGION:-sa-east-1}"
PROJECT_NAME="${PROJECT_NAME:-dispute-factored}"
BOOTSTRAP_STACK="${PROJECT_NAME}-bootstrap"
APPLICATION_STACK="${PROJECT_NAME}-demo"
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo local)"
IMAGE_TAG="${IMAGE_TAG:-${GIT_SHA}-$(date +%Y%m%d%H%M%S)}"
LANGSMITH_SECRET_ID="${LANGSMITH_SECRET_ID:-${PROJECT_NAME}/langsmith}"
LANGSMITH_PROJECT="${LANGSMITH_PROJECT:-${PROJECT_NAME}}"

stack_output() {
  aws cloudformation describe-stacks \
    --region "${AWS_REGION}" \
    --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" \
    --output text
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
elif [[ "${ACTION}" == "application" ]]; then
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
  TEMP_CUSTOMERS_CONTEXT=""
  DATA_CONTAINER_ID=""
  export DOCKER_CONFIG="${DEPLOY_DOCKER_CONFIG}"
  cleanup() {
    if [[ -n "${DATA_CONTAINER_ID}" ]]; then
      docker rm -f "${DATA_CONTAINER_ID}" >/dev/null 2>&1 || true
    fi
    if [[ -n "${TEMP_CUSTOMERS_CONTEXT}" && \
      "$(basename "${TEMP_CUSTOMERS_CONTEXT}")" == dispute-customers.* ]]; then
      rm -rf -- "${TEMP_CUSTOMERS_CONTEXT}"
    fi
    if [[ "$(basename "${DEPLOY_DOCKER_CONFIG}")" == dispute-docker-config.* ]]; then
      rm -rf -- "${DEPLOY_DOCKER_CONFIG}"
    fi
  }
  trap cleanup EXIT

  aws ecr get-login-password --region "${AWS_REGION}" | \
    python3 infra/aws/write_docker_auth.py "${DOCKER_CONFIG}/config.json" "${REGISTRY}"

  CUSTOMERS_BUILD_CONTEXT="${CUSTOMERS_BUILD_CONTEXT:-../data/raw}"
  if [[ ! -f "${CUSTOMERS_BUILD_CONTEXT}/customers.csv" ]]; then
    REPOSITORY_NAME="${REPOSITORY_URI#*/}"
    BASE_IMAGE_TAG="$(aws ecr describe-images \
      --region "${AWS_REGION}" \
      --repository-name "${REPOSITORY_NAME}" \
      --filter tagStatus=TAGGED \
      --query 'reverse(sort_by(imageDetails,&imagePushedAt))[0].imageTags[0]' \
      --output text)"
    if [[ -z "${BASE_IMAGE_TAG}" || "${BASE_IMAGE_TAG}" == "None" ]]; then
      echo "customers.csv is unavailable and ECR has no prior image to recover it from." >&2
      echo "Set CUSTOMERS_BUILD_CONTEXT to a directory containing customers.csv for the first deploy." >&2
      exit 1
    fi

    BASE_IMAGE_URI="${REPOSITORY_URI}:${BASE_IMAGE_TAG}"
    TEMP_CUSTOMERS_CONTEXT="$(mktemp -d "${TMPDIR:-/tmp}/dispute-customers.XXXXXX")"
    docker pull "${BASE_IMAGE_URI}" >/dev/null
    DATA_CONTAINER_ID="$(docker create "${BASE_IMAGE_URI}")"
    docker cp \
      "${DATA_CONTAINER_ID}:/var/task/demo_data/customers.csv" \
      "${TEMP_CUSTOMERS_CONTEXT}/customers.csv"
    docker rm "${DATA_CONTAINER_ID}" >/dev/null
    DATA_CONTAINER_ID=""
    CUSTOMERS_BUILD_CONTEXT="${TEMP_CUSTOMERS_CONTEXT}"
    echo "Recovered the synthetic customer table from the previous immutable ECR image."
  fi

  docker buildx build \
    --platform linux/amd64 \
    --file Dockerfile.aws \
    --build-context synthetic_data="${CUSTOMERS_BUILD_CONTEXT}" \
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
      LangSmithProject="${LANGSMITH_PROJECT}"

  echo "Image: ${IMAGE_URI}"
  echo "LangSmith project: ${LANGSMITH_PROJECT}"
  echo "Webhook: $(stack_output "${APPLICATION_STACK}" OpenAIWebhookUrl)"
else
  echo "Usage: $0 bootstrap|application" >&2
  exit 2
fi
