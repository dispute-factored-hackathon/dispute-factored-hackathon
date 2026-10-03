# PostgreSQL and DuckDB deployment access for a partner

Use this document as the handoff guide for the authorized database deployment partner.

This access is intentionally limited to deploying the project's PostgreSQL database and a
private S3 artifact bucket for DuckDB in the AWS account owned by the project. It cannot deploy
Lambda functions, edit IAM permissions,
read the OpenAI or LangSmith secrets, push container images, or operate other CloudFormation
stacks.

## Authorized boundary

- AWS account: `832271495954`
- Region: `sa-east-1` (São Paulo)
- Authorized CloudFormation stacks: `dispute-factored-postgres` and `dispute-factored-duckdb`
- Execution role: `arn:aws:iam::832271495954:role/dispute-factored-database-cfn-execution`
- IAM user: `dispute-factored-database-deployer`
- RDS identifiers must start with `dispute-factored-postgres`.
- Secrets must be under `dispute-factored/postgres/`.
- Security groups must have the tag `Project=dispute-factored`.
- DuckDB files must be stored under `s3://dispute-factored-duckdb-832271495954-sa-east-1/duckdb/`.

The deployer can submit and execute changes only for that stack. CloudFormation performs the
actual RDS, Secrets Manager, and security-group operations through the restricted execution
role. The deployer cannot pass any other IAM role.

## Receive the credentials safely

The owner must send the access key ID and secret access key through an encrypted channel or a
password manager. Do not send them in a GitHub issue, pull request, chat room, email body, or
commit. The secret access key is shown only once when it is created.

On the owner's Mac, the validated credential is stored in Keychain as an encoded JSON value.
Copy the decoded JSON directly to the clipboard with the following command, then paste it into a
password-manager item shared only with the partner:

```bash
security find-generic-password \
  -a dispute-factored-database-deployer \
  -s aws-dispute-factored-database-deployer \
  -w | base64 -D | pbcopy
```

This command intentionally does not print the secret in the terminal. The shared JSON contains
`AccessKeyId` and `SecretAccessKey` inside its `AccessKey` object.

Configure a dedicated local profile:

```bash
aws configure --profile factored-database-deployer
```

Enter the supplied values and use:

- Default region: `sa-east-1`
- Output format: `json`

Verify the identity before deploying:

```bash
aws sts get-caller-identity --profile factored-database-deployer
```

The ARN must end with `user/dispute-factored-database-deployer` and the account must be
`832271495954`. Stop if either value differs.

## Requirements for the database template

The CloudFormation template may contain only the PostgreSQL-related resources covered by the
access boundary: RDS DB instances, DB subnet or parameter groups, one or more tagged security
groups, and Secrets Manager secrets under the authorized prefix.

Use the following conventions:

1. Use PostgreSQL as the RDS engine.
2. Keep the database private (`PubliclyAccessible: false`).
3. Encrypt storage and enable deletion protection for any non-ephemeral environment.
4. Let Secrets Manager generate the master password; never place a password in the template.
5. Prefix every RDS identifier with `dispute-factored-postgres`.
6. Name secrets under `dispute-factored/postgres/`.
7. Add the tag `Project=dispute-factored` to the stack and every taggable resource.
8. Avoid a NAT Gateway unless the architecture demonstrably requires it; it adds ongoing cost.
9. Use the smallest instance/storage configuration appropriate for the hackathon and review the
   AWS pricing estimate before deployment.

## Validate and deploy

From the directory containing the database template:

```bash
aws cloudformation validate-template \
  --profile factored-database-deployer \
  --region sa-east-1 \
  --template-body file://postgres.yaml

aws cloudformation deploy \
  --profile factored-database-deployer \
  --region sa-east-1 \
  --stack-name dispute-factored-postgres \
  --template-file postgres.yaml \
  --role-arn arn:aws:iam::832271495954:role/dispute-factored-database-cfn-execution \
  --tags Project=dispute-factored
```

The credentials are deliberately unable to deploy a differently named stack or use another
execution role. If a permission error occurs, do not broaden the user policy. Share the failed
CloudFormation event with the project owner so the missing operation can be reviewed narrowly.

## Deploy DuckDB storage

DuckDB is an embedded database file, not a managed database server. For this project, deployment
means creating one private, encrypted, public-access-blocked S3 bucket and uploading versioned
`.duckdb` artifacts under its `duckdb/` prefix. The application or analytics runtime that reads
the file should be defined separately; these credentials cannot deploy compute services.

The DuckDB CloudFormation template must create exactly this bucket:

```text
dispute-factored-duckdb-832271495954-sa-east-1
```

Validate and deploy it with the same execution role:

```bash
aws cloudformation validate-template \
  --profile factored-database-deployer \
  --region sa-east-1 \
  --template-body file://duckdb.yaml

aws cloudformation deploy \
  --profile factored-database-deployer \
  --region sa-east-1 \
  --stack-name dispute-factored-duckdb \
  --template-file duckdb.yaml \
  --role-arn arn:aws:iam::832271495954:role/dispute-factored-database-cfn-execution \
  --tags Project=dispute-factored
```

Upload the database file only after the bucket stack is ready:

```bash
aws s3 cp analytics.duckdb \
  s3://dispute-factored-duckdb-832271495954-sa-east-1/duckdb/analytics.duckdb \
  --profile factored-database-deployer \
  --region sa-east-1
```

The deployer cannot upload objects outside `duckdb/` and cannot access unrelated buckets.

## After deployment

Send the owner:

- the CloudFormation stack ARN;
- the RDS endpoint and port;
- the database name;
- the Secrets Manager secret ARN (not the password);
- the VPC, subnet-group, and security-group identifiers;
- the estimated monthly cost and selected backup/retention settings.

Do not send or commit the database password. The application owner should grant the application
runtime access to the secret separately.

## Revoke access

When the partner finishes, the owner should deactivate and then delete the access key. The IAM
user can remain without an active key for audit history, or the whole access stack can be removed
after the database stack no longer depends on its execution role.
