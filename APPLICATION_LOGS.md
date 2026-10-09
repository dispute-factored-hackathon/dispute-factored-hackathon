# Application logs and traces

This guide explains where each type of diagnostic information lives and how a project colleague can read it. The AWS credential supplied separately has least-privilege, read-only access to the deployed application's CloudWatch logs in `sa-east-1`. It does not contain permission to change or delete logs, invoke Lambda functions, read application secrets, or access unrelated log groups.

Never add an AWS access key, secret key, Twilio token, OpenAI key, or LangSmith key to this file or to Git. Configure credentials locally and send secrets through an approved private channel.

## Quick reference

| What you need | Location | Identifier | Access required |
|---|---|---|---|
| Voice agent, SIP webhook, Realtime events, call transcript telemetry, handoff, transaction search, Visa classification, complaint filing, and card blocking | AWS CloudWatch Logs | `/aws/lambda/dispute-factored-demo-sip` | Supplied AWS credential |
| Web application runtime and Lambda errors | AWS CloudWatch Logs | `/aws/lambda/dispute-factored-demo-web` | Supplied AWS credential |
| Judge startup, web/data readiness and idle egress shutdown | AWS CloudWatch Logs | `/aws/lambda/dispute-factored-demo-judge-wake` | Project AWS access |
| PostgreSQL and DuckDB deployment progress | AWS CloudFormation stack events | `dispute-factored-postgres` and `dispute-factored-duckdb` | Supplied AWS credential |
| Pull-request tests, security scans, and releases | GitHub Actions | Repository **Actions** tab | GitHub repository access |
| PSTN call status, duration, routing, and Twilio errors | Twilio Console | **Monitor > Logs > Calls** | Twilio project access |
| Agent/model execution traces | LangSmith | Project `dispute-factored` | LangSmith workspace access |
| OpenAI API usage and project activity | OpenAI Platform | The OpenAI project used by the demo | OpenAI project access |
| Local API, CLI, and test output | Terminal standard output/error | The local process | Local machine only |

AWS credentials do not grant access to Twilio, GitHub, LangSmith, or the OpenAI Platform. Those services require their own accounts and roles.

## 1. Configure the restricted AWS credential

Install AWS CLI v2, then create a dedicated profile. Enter the access key ID and secret access key that were sent privately:

```bash
aws configure --profile dispute-factored-colleague
```

Use these values when prompted:

```text
Default region name: sa-east-1
Default output format: json
```

Confirm which identity is active:

```bash
aws sts get-caller-identity --profile dispute-factored-colleague
```

The ARN should end with `user/dispute-factored-database-deployer`. If it does not, stop and verify the profile before continuing.

For a terminal session, these optional environment variables shorten the commands:

```bash
export AWS_PROFILE=dispute-factored-colleague
export AWS_REGION=sa-east-1
```

## 2. Read the AWS application logs

The deployed demo has separate voice, web, database-bootstrap and judge-wake Lambda log groups. Application groups retain logs according to the CloudFormation setting. Use a narrow time range whenever possible.

List the available application groups:

```bash
aws logs describe-log-groups \
  --region sa-east-1 \
  --log-group-name-prefix /aws/lambda/dispute-factored-demo \
  --query 'logGroups[].{name:logGroupName,retentionDays:retentionInDays,storedBytes:storedBytes}' \
  --output table
```

### Voice and telephone calls

Show the last 30 minutes:

```bash
aws logs tail /aws/lambda/dispute-factored-demo-sip \
  --region sa-east-1 \
  --since 30m \
  --format short
```

Follow a call while testing it:

```bash
aws logs tail /aws/lambda/dispute-factored-demo-sip \
  --region sa-east-1 \
  --since 5m \
  --follow \
  --format short
```

Stop following with `Ctrl+C`. CloudWatch does not guarantee exact ordering across different streams, so use `call_id`, timestamps, and event names together when reconstructing a call.

Useful searches:

```bash
# One call, after copying its call_id from a recent event
aws logs tail /aws/lambda/dispute-factored-demo-sip \
  --region sa-east-1 --since 3h --filter-pattern '"CALL_ID_HERE"'

# Customer and Izzy transcript telemetry
aws logs tail /aws/lambda/dispute-factored-demo-sip \
  --region sa-east-1 --since 3h --filter-pattern '"voice.transcript.completed"'

# Authentication decisions
aws logs tail /aws/lambda/dispute-factored-demo-sip \
  --region sa-east-1 --since 3h --filter-pattern '"voice.authentication"'

# Transaction-search events
aws logs tail /aws/lambda/dispute-factored-demo-sip \
  --region sa-east-1 --since 3h --filter-pattern '"voice.transaction"'

# Classifications, complaints, card blocks, and handoffs
aws logs tail /aws/lambda/dispute-factored-demo-sip \
  --region sa-east-1 --since 3h --filter-pattern '"voice.dispute"'
aws logs tail /aws/lambda/dispute-factored-demo-sip \
  --region sa-east-1 --since 3h --filter-pattern '"voice.complaint"'
aws logs tail /aws/lambda/dispute-factored-demo-sip \
  --region sa-east-1 --since 3h --filter-pattern '"voice.card"'
aws logs tail /aws/lambda/dispute-factored-demo-sip \
  --region sa-east-1 --since 3h --filter-pattern '"handoff"'

# Runtime failures and Python tracebacks
aws logs tail /aws/lambda/dispute-factored-demo-sip \
  --region sa-east-1 --since 3h --filter-pattern '"ERROR"'
aws logs tail /aws/lambda/dispute-factored-demo-sip \
  --region sa-east-1 --since 3h --filter-pattern '"Traceback"'
```

Common structured events include:

- `webhook.*`: receipt and validation of the OpenAI incoming-call webhook;
- `worker.*`: asynchronous Lambda worker startup, completion, or failure;
- `sip.*` and `realtime.*`: SIP acceptance, sideband connection, audio, model responses, and DTMF;
- `voice.stage.transition`: movement through the call workflow;
- `voice.authentication.*`: authentication method and result;
- `transaction.search.completed` and `voice.transaction.*`: retrieval, ranking, proposal, confirmation, and exhaustion;
- `dispute.classification.completed` and `voice.dispute.*`: dispute classification and Visa-code state;
- `voice.complaint.*`, `voice.card.*`, and `voice.handoff.*`: consequential actions and escalation;
- `jev.decision.*`: Jev routing result, confidence, latency, or fallback.

The demo currently enables complete call transcript telemetry because it uses synthetic data. Treat it as sensitive anyway: do not paste a transcript into a public issue, pull request, or chat. DTMF document digits are intentionally not written to logs.

### Web application

Show recent web runtime logs:

```bash
aws logs tail /aws/lambda/dispute-factored-demo-web \
  --region sa-east-1 \
  --since 30m \
  --format short
```

Follow the web Lambda while reproducing a failure:

```bash
aws logs tail /aws/lambda/dispute-factored-demo-web \
  --region sa-east-1 \
  --since 5m \
  --follow \
  --format short
```

Lambda platform records such as `START`, `END`, and `REPORT` show invocation boundaries, duration, memory, and failures. Application tracebacks appear in the same group.

### Judge startup and idle shutdown

Inspect the on-demand controller when the GitHub Pages screen does not redirect, or when the egress instance does not stop after inactivity:

```bash
aws logs tail /aws/lambda/dispute-factored-demo-judge-wake \
  --region sa-east-1 \
  --since 30m \
  --format short
```

The controller starts the egress instance on a browser wake request, synchronously warms the web/data Lambda after EC2 is running, and checks recent web and voice invocation metrics on the EventBridge schedule. If CloudWatch activity cannot be read, it deliberately keeps egress running rather than interrupting a judge or telephone call.

### CloudWatch Logs Insights

For multi-event investigations, open **CloudWatch > Logs Insights** in region **South America (São Paulo) / `sa-east-1`**, select only the `sip` or `web` group, and use a short time window. Example query for one telephone call:

```text
fields @timestamp, @message
| filter @message like /CALL_ID_HERE/
| sort @timestamp asc
| limit 500
```

Example query for recent failures:

```text
fields @timestamp, @logStream, @message
| filter @message like /ERROR|Exception|Traceback|failed/
| sort @timestamp desc
| limit 200
```

Example query for the application-controlled portion of voice cold starts:

```text
fields @timestamp, @message
| filter @message like /sip.gateway.initialized|webhook.gateway.ready|aws.secret.loaded/
| sort @timestamp desc
| limit 100
```

For the SIP Lambda, compare `webhook.gateway.ready` with `webhook.handler.started`, `worker.started`, `sip.accept.completed`, `realtime.sideband.connected`, and first-response events. SnapStart only addresses Lambda initialization; these timestamps distinguish application setup from OpenAI, SIP, database and model-response latency. The deployed function keeps Lambda system logging at `WARN` to limit log volume, so platform `REPORT` records and `@restoreDuration` are not normally emitted. Temporarily use `INFO` only when a platform-level benchmark is required.

Logs Insights charges for data scanned. Select one log group, keep the time range small, and avoid repeatedly querying all retained data. The restricted credential can query only the web and voice application groups; the judge-wake group requires project AWS access.

AWS references: [CloudWatch Logs permissions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/permissions-reference-cwl.html), [`aws logs tail`](https://docs.aws.amazon.com/cli/latest/reference/logs/tail.html), and [`aws logs start-query`](https://docs.aws.amazon.com/cli/latest/reference/logs/start-query.html).

## 3. Read deployment events

CloudFormation events explain failed PostgreSQL and DuckDB deployments. They are not Lambda application logs.

```bash
aws cloudformation describe-stack-events \
  --region sa-east-1 \
  --stack-name dispute-factored-postgres \
  --max-items 50 \
  --output table

aws cloudformation describe-stack-events \
  --region sa-east-1 \
  --stack-name dispute-factored-duckdb \
  --max-items 50 \
  --output table
```

The colleague credential can inspect and deploy only these named database stacks. It cannot deploy the web or voice application stack.

## 4. GitHub Actions logs

Open the repository's [Actions page](https://github.com/dispute-factored-hackathon/factored-hackathon-2026-ateam/actions) to inspect pull-request validation and deployments. With GitHub CLI authenticated to an authorized account:

```bash
gh run list --repo dispute-factored-hackathon/factored-hackathon-2026-ateam --limit 20
gh run view RUN_ID --repo dispute-factored-hackathon/factored-hackathon-2026-ateam --log-failed
```

Relevant workflows include Python tests and Ruff, Semgrep, Gitleaks, SonarQube, and AWS deployment. GitHub redacts configured Actions secrets, but logs must still not print credentials intentionally.

## 5. Twilio call logs

Twilio is the source of truth for the telephone leg before it reaches OpenAI. In the Twilio Console, use **Monitor > Logs > Calls**, open the latest call, and record:

- Call SID;
- originating and destination numbers;
- start time, duration, and final status;
- SIP response/error codes;
- request inspector warnings.

Use the timestamp and Call SID to align Twilio with the `call_id` and timestamps in the SIP CloudWatch group. Twilio access is separate from AWS; ask the project owner for an appropriate Twilio role instead of sharing the owner password or Auth Token.

## 6. LangSmith traces

The deployed voice agent sends traces to the LangSmith project `dispute-factored`. LangSmith is best for model/tool sequencing, latency, inputs, outputs, and nested agent spans. Filter by the approximate call time and the trace metadata (`channel=sip`, application, and workflow/group identifiers).

Trace payloads may include synthetic customer utterances and model output. Do not expose them publicly. The AWS colleague credential does not grant LangSmith access and does not allow reading the LangSmith secret from Secrets Manager.

## 7. OpenAI project activity

Use the OpenAI Platform project that owns the Realtime API key for API usage and project-level activity. The detailed operational sequence used by this application is intentionally captured in CloudWatch and LangSmith, which provide the application's `call_id` correlation. OpenAI access must be granted as a project role; never send the API key as a substitute for account access.

## 8. Local development logs

Run the web application with an explicit log level:

```bash
cd visa-dispute-hackathon
LOG_LEVEL=DEBUG uv run uvicorn webapp.backend.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --log-level debug
```

Run tests with captured output visible:

```bash
uv run pytest -q -s
```

Local output is not uploaded automatically. Remove secrets and any customer information before sharing a snippet.

## Investigation checklist

1. Record the problem's local time, timezone, channel (`web` or `phone`), and expected result.
2. For a telephone issue, start with Twilio status, then find the same time in the SIP CloudWatch group.
3. Copy the `call_id` from CloudWatch and use it for the complete application timeline.
4. Use LangSmith only when the failure concerns model/tool reasoning or latency.
5. Use the web log group for HTTP/Lambda failures and CloudFormation events for database-deployment failures.
6. Share the smallest relevant excerpt; never share credentials or complete transcripts publicly.
