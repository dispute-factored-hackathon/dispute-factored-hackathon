# Review automation setup

The repository contains configuration for deterministic Python checks, Dependabot, Codecov,
Semgrep, Gitleaks, CodeRabbit and SonarQube Cloud. No service should receive real customer or banking
data. The codebase and fixtures are synthetic.

## Active without an external account

- **Ruff, unittest, Coverage and Radon:** run in `python-quality.yml`. Coverage must remain at least
  75%; complexity and maintainability are printed in the workflow log.
- **Dependabot:** GitHub reads `.github/dependabot.yml` after it reaches the default branch. It opens
  weekly grouped Python and GitHub Actions updates.
- **Semgrep:** `security.yml` runs the public Python and security-audit rules in the GitHub runner.

## Codecov free private-repository plan

1. Visit <https://app.codecov.io/login/gh> and authorize GitHub.
2. Select `dispute-factored-hackathon/dispute-factored-hackathon`.
3. Copy the repository upload token.
4. In GitHub, open **Settings → Secrets and variables → Actions → New repository secret**.
5. Create `CODECOV_TOKEN` with the copied value.

Codecov's Developer plan currently allows one user, unlimited private repositories and 250 private
uploads per month. The workflow does not block PRs when Codecov is not configured; local coverage
still remains a required check.

## Semgrep free edition

The checked-in workflow runs without an account. To get the hosted findings dashboard, automatic
triage and PR integration:

1. Visit <https://semgrep.dev/login> and sign in with GitHub.
2. Connect the organization and select this repository.
3. Follow Semgrep's generated onboarding PR or add its token as `SEMGREP_APP_TOKEN` if requested.

The current free edition supports up to 10 private repositories and 10 contributors.

## Gitleaks organization license or trial

The open-source scanner is free locally. The official GitHub Action asks organizations using private
repositories for `GITLEAKS_LICENSE`.

1. Install the Gitleaks GitHub application from <https://github.com/apps/gitleaks>.
2. Request the organization trial/license from <https://gitleaks.io/>.
3. Store the provided license as the GitHub Actions secret `GITLEAKS_LICENSE`.
4. Add the repository Actions variable `GITLEAKS_ENABLED` with value `true`.

The workflow is skipped until `GITLEAKS_ENABLED=true`. Until the license is present, run the
open-source CLI locally before committing secrets. Never add a real `.env` file to Git.

## CodeRabbit 14-day private-repository trial

1. Visit <https://app.coderabbit.ai/> and sign in with GitHub.
2. Choose the `dispute-factored-hackathon` organization.
3. Start the 14-day Team trial; CodeRabbit states that no credit card is required.
4. Install the CodeRabbit GitHub App for only this repository.
5. Open or update a pull request. `.coderabbit.yaml` enables automatic assertive reviews.
6. To request another pass after fixes, comment `@coderabbitai review` on the pull request.

After the trial, reviews of a private repository require a paid plan. Disable usage-based add-ons in
CodeRabbit's subscription settings if the team does not want possible overage charges.

## SonarQube Cloud free allowance or trial

1. Visit <https://sonarcloud.io/> and sign in with GitHub.
2. Import the GitHub organization and repository.
3. Confirm the generated project key matches
   `dispute-factored-hackathon_dispute-factored-hackathon`; adjust `sonar-project.properties` if it
   differs.
4. Create a Sonar token and store it as the GitHub Actions secret `SONAR_TOKEN`.
5. Add the repository Actions variable `SONAR_ENABLED` with value `true`.
6. Select the free private-code allowance when available, or start the offered Team trial.

The workflow is skipped until `SONAR_ENABLED=true`, so an unconfigured external account cannot block
pull requests.

## Recommended required checks

Require `Ruff and tests (Python 3.11)`, `Semgrep SAST`, and `Gitleaks secrets` before merge once each
service is confirmed working. Add Codecov, CodeRabbit and SonarQube gates only after their accounts,
privacy settings and billing controls have been reviewed by an organization administrator.
