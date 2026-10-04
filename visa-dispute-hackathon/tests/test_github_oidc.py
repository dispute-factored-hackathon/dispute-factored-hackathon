from pathlib import Path

ROLE_TEMPLATE = Path("infra/aws/github-actions-role.yaml")
EXPECTED_REPOSITORY_SUBJECT = (
    "repo:${GitHubOrganization}@${GitHubOrganizationId}/${GitHubRepository}@${GitHubRepositoryId}"
)


def test_github_oidc_trust_uses_immutable_repository_identity() -> None:
    template = ROLE_TEMPLATE.read_text(encoding="utf-8")

    assert 'Default: "334323685"' in template
    assert 'Default: "1389807294"' in template
    assert f"{EXPECTED_REPOSITORY_SUBJECT}:pull_request" in template
    assert f"{EXPECTED_REPOSITORY_SUBJECT}:ref:refs/heads/main" in template
    assert f"{EXPECTED_REPOSITORY_SUBJECT}:ref:refs/tags/*" in template
    assert "repo:${GitHubOrganization}/${GitHubRepository}:" not in template
    assert "cloudformation:ValidateTemplate" in template
    assert "secretsmanager:DescribeSecret" in template
    assert "secret:${ProjectName}/langsmith-*" in template
