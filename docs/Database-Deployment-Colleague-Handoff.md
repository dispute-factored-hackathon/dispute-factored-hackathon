# Database deployment handoff

Hello! You are receiving restricted AWS credentials to deploy the database layer for the
Factored dispute hackathon project. This document is the complete handoff for PostgreSQL and
DuckDB.

The credentials will be shared separately through a password manager. They must never be placed
in this document, a repository, pull request, issue, chat message, terminal screenshot, notebook,
or application configuration committed to Git.

## Objective

Deploy two independent data resources in the project owner's AWS account:

1. A private PostgreSQL database using Amazon RDS.
2. A private S3 bucket for versioned DuckDB database files.

DuckDB is an embedded database, not a managed database server. In this handoff, deploying DuckDB
means deploying its private storage and uploading a `.duckdb` artifact. A runtime or API that
queries that file is outside this permission set and must be discussed separately.

## Authorized AWS boundary

| Setting | Authorized value |
|---|---|
| AWS account | `832271495954` |
| Region | `sa-east-1` — São Paulo |
| IAM user | `dispute-factored-database-deployer` |
| CloudFormation execution role | `arn:aws:iam::832271495954:role/dispute-factored-database-cfn-execution` |
| PostgreSQL stack | `dispute-factored-postgres` |
| DuckDB stack | `dispute-factored-duckdb` |
| DuckDB bucket | `dispute-factored-duckdb-832271495954-sa-east-1` |
| DuckDB upload prefix | `s3://dispute-factored-duckdb-832271495954-sa-east-1/duckdb/` |
| Required resource tag | `Project=dispute-factored` |

The credentials cannot administer IAM, deploy Lambda or ECS, access unrelated S3 buckets,
operate differently named CloudFormation stacks, read the OpenAI or LangSmith secrets, or use a
different CloudFormation execution role.

## 1. Configure the AWS profile

The password-manager item contains an `AccessKey` object with `AccessKeyId` and
`SecretAccessKey` fields. Configure a dedicated profile:

```bash
aws configure --profile factored-database-deployer
```

Enter:

- AWS Access Key ID: the received `AccessKeyId` value;
- AWS Secret Access Key: the received `SecretAccessKey` value;
- Default region: `sa-east-1`;
- Default output format: `json`.

Do not configure these credentials as the default profile.

Verify the identity:

```bash
aws sts get-caller-identity \
  --profile factored-database-deployer
```

Expected account and ARN:

```text
Account: 832271495954
Arn: arn:aws:iam::832271495954:user/dispute-factored-database-deployer
```

Stop and contact the project owner if either value differs.

## 2. Prepare the PostgreSQL template

Create a CloudFormation template named `postgres.yaml`. It may contain only the PostgreSQL
resources covered by this handoff:

- an RDS PostgreSQL DB instance;
- a DB subnet group;
- a PostgreSQL parameter group when required;
- security groups dedicated to the database;
- a Secrets Manager secret under `dispute-factored/postgres/`.

Mandatory design requirements:

1. Set the database engine to PostgreSQL.
2. Prefix every RDS identifier with `dispute-factored-postgres`.
3. Set `PubliclyAccessible: false`.
4. Encrypt storage.
5. Generate the master password in Secrets Manager. Do not place a password in the template or
   pass it as a plaintext parameter.
6. Apply `Project=dispute-factored` to the stack and every taggable resource.
7. Use private subnets and restrict inbound port `5432` to the application security group or an
   explicitly approved private source. Never use `0.0.0.0/0`.
8. Enable deletion protection for a persistent environment. If this is intentionally ephemeral,
   document that decision and the cleanup date.
9. Select the smallest instance and storage configuration suitable for the hackathon.
10. Do not add a NAT Gateway without approval because it creates ongoing cost.

Validate the template:

```bash
aws cloudformation validate-template \
  --profile factored-database-deployer \
  --region sa-east-1 \
  --template-body file://postgres.yaml
```

Deploy it:

```bash
aws cloudformation deploy \
  --profile factored-database-deployer \
  --region sa-east-1 \
  --stack-name dispute-factored-postgres \
  --template-file postgres.yaml \
  --role-arn arn:aws:iam::832271495954:role/dispute-factored-database-cfn-execution \
  --tags Project=dispute-factored
```

Inspect failures without broadening permissions:

```bash
aws cloudformation describe-stack-events \
  --profile factored-database-deployer \
  --region sa-east-1 \
  --stack-name dispute-factored-postgres \
  --max-items 20
```

If an operation is denied, send the failed event and requested action to the owner. Do not ask for
administrator access or modify the access policy yourself.

## 3. Prepare the DuckDB storage template

Create a CloudFormation template named `duckdb.yaml`. It should create exactly one S3 bucket:

```text
dispute-factored-duckdb-832271495954-sa-east-1
```

The bucket must:

- block all public access;
- use server-side encryption;
- enable versioning;
- carry the tag `Project=dispute-factored`;
- contain no website-hosting or public bucket policy;
- avoid unnecessary replication or lifecycle costs.

Validate the template:

```bash
aws cloudformation validate-template \
  --profile factored-database-deployer \
  --region sa-east-1 \
  --template-body file://duckdb.yaml
```

Deploy it:

```bash
aws cloudformation deploy \
  --profile factored-database-deployer \
  --region sa-east-1 \
  --stack-name dispute-factored-duckdb \
  --template-file duckdb.yaml \
  --role-arn arn:aws:iam::832271495954:role/dispute-factored-database-cfn-execution \
  --tags Project=dispute-factored
```

Upload the database file only under the authorized prefix:

```bash
aws s3 cp analytics.duckdb \
  s3://dispute-factored-duckdb-832271495954-sa-east-1/duckdb/analytics.duckdb \
  --profile factored-database-deployer \
  --region sa-east-1
```

Confirm the uploaded artifact:

```bash
aws s3 ls \
  s3://dispute-factored-duckdb-832271495954-sa-east-1/duckdb/ \
  --profile factored-database-deployer \
  --region sa-east-1
```

The credentials cannot upload outside `duckdb/` or access unrelated buckets.

## 4. Required handback

After both deployments, send the owner the following information without including passwords:

### PostgreSQL

- CloudFormation stack ARN and final status;
- RDS instance identifier, endpoint, port, engine version, and database name;
- Secrets Manager secret ARN, never the secret value;
- VPC, subnet-group, and security-group identifiers;
- instance class, allocated storage, backup retention, deletion protection, and estimated monthly
  cost;
- migrations or initialization steps that still need to run.

### DuckDB

- CloudFormation stack ARN and final status;
- S3 bucket ARN;
- uploaded object key, file size, version ID, and checksum;
- DuckDB version used to create the file;
- tables, schemas, and data-generation or ingestion steps;
- estimated storage cost and any lifecycle policy.

## 5. Completion and credential revocation

Tell the owner when all deployment and verification work is complete. The access key is temporary
project access and will be deactivated and deleted after handoff. Do not continue using or copying
the credentials after completion.

If you suspect the credentials were exposed, stop immediately and ask the owner to revoke them.
Do not attempt further deployment with a potentially compromised key.
