# Optional AWS adapter: design only, undeployed

The working product is the offline CLI. The Lambda adapter and SAM template are
an optional extension tested with injected I/O. No AWS API calls, deployment,
account connection or integration test has been performed. Local cfn-lint checks
structure and SAM transformation; it cannot establish that deployment succeeds.

## What each service does

S3 holds UTF-8 synthetic JSONL/CSV objects under `incoming/`. Object-created
notifications invoke Lambda. Lambda reads one object at a time, calls the same
parser and rules as the CLI, and prints one aggregate JSON summary per object.
CloudWatch Logs receives stdout and Lambda's operational messages. CloudFormation
with the SAM transform describes these resources; IAM gives the function its
specific read/log permissions. There is no database, web API, VPC or ML service.

The template sets 256 MB memory, a 15-second timeout, reserved concurrency of two,
one asynchronous retry and a ten-minute maximum event age. These are conservative
demo limits, not benchmarked capacity guarantees. Each invocation accepts 1-10
S3 records. Each object is capped at 1 MiB, 5,000 physical event rows, 16 KiB per
line and 500 findings. Bounds can be lowered via `RULE_CONFIG_JSON`; they cannot
exceed the adapter caps. File and line caps include newline bytes.

S3 event records must identify the configured bucket, event version 2.x and a
supported `ObjectCreated` operation. URL-decoded keys must be flat filenames
matching `incoming/[A-Za-z0-9][A-Za-z0-9_.-]{0,119}.jsonl` (or `.csv`), with no
`..`. Metadata must include a lowercase hex ETag (optionally multipart) and a
nonnegative integer size. Encoded separators are decoded once before validation.
Subdirectories, spaces and other extensions are rejected. A real S3 test-event
envelope is also rejected; it does not contain analyzable records.

Every record's envelope is checked before any fetch. `GetObject` uses `IfMatch`
with the event ETag, checks `ContentLength`, reads at most cap+1 bytes, checks the
actual length against the event size, and closes the body even on failure. There
is no file download, temporary object path or archive decompression.

## Baselines and privacy

The template's `RULE_CONFIG_JSON` is `{}`: defaults enable burst/spray rules and
leave unusual-source alerts disabled. A future reviewed deployment can set an
explicit per-user `baseline` in that configuration, using the CLI schema. Lambda
environment values have service-level size limits; use only a small synthetic
baseline here. The adapter never learns trust from incoming objects.

Summaries contain schema version, event/duplicate/finding counts, per-rule counts,
and a SHA-256 `object_id` derived from bucket/key/ETag. They exclude raw events,
usernames, IPs, timestamps, bucket names, keys and explanations. Each summary is
at most 2,048 UTF-8 bytes. The digest supports correlation; it is not a secret-key
hash or a guarantee against guessing predictable object names. SDK/validation
exceptions are replaced with a fixed runtime error so sensitive values are not
printed in error messages. Do not enable SDK debug logging for raw inputs.

## Permissions and storage controls

The function can only `s3:GetObject` under
`arn:<partition>:s3:::<account>-<region>-lad-synthetic-input/incoming/*`. It has no
list, write or delete access, and no broad AWS managed execution policy. Its only
log actions are `logs:CreateLogStream` and `logs:PutLogEvents`, scoped to streams
under `/aws/lambda/<FunctionName>`. The log group is created by the template;
Lambda does not need `logs:CreateLogGroup`. An explicit Lambda invocation
permission restricts S3 to this bucket ARN and source account. The native bucket
notification depends on that permission. Static, account/region-specific bucket
ARNs avoid a circular reference and avoid SAM's broader account-only S3
permission generation. Review the generated change set before any future
deployment.

The `*` suffix in each allow resource covers objects in that one prefix or
streams in that one group. The bucket policy uses `Principal: '*'` and `s3:*`
only in a **Deny** of non-TLS requests to this bucket and its objects. It grants
no access. Bucket public access is blocked, ACLs are disabled with bucket-owner
enforcement, and SSE-S3 AES256 encryption is explicit. S3 expires incoming objects
after seven days and aborts incomplete multipart uploads after one day;
CloudWatch retention is fourteen days. The bucket and log group are retained if
the stack is removed; retention/lifecycle cleanup is asynchronous and requires
later owner review. SSE-S3 avoids introducing KMS permissions or key costs.

The notification prefix and absence of any function S3 writes prevent an output
feedback loop. Unsupported uploads under `incoming/` can still invoke Lambda
and fail validation, so future upload permissions must also be narrowly scoped.
Upload/administrative permissions are deliberately absent from the runtime role.

## Failures, ordering and duplicate delivery

Rules operate per object. They do not correlate windows across files or remember
past invocations. Rows within an object are sorted and deduplicated, as in the
CLI. S3 notifications can arrive out of order and more than once. Exact duplicate
object references in one invocation are processed once; there is no durable
idempotency store across invocations. The same object can therefore produce the
same summary repeatedly. Downstream consumers can deduplicate by `object_id`.
Different keys with identical bytes still have different object identities.

`IfMatch` rejects most overwritten-object races, but ETags are not immutable
version IDs or always content hashes. Versioning is not enabled and there is no
`GetObjectVersion` permission. Use unique keys; identical ETag overwrites and
same-size changes are limitations of this small adapter. A future version could
process explicit version IDs and retain idempotency records.

Malformed content, cap exhaustion or a fetch failure fails the invocation; the
handler does not acknowledge it as a successful analysis. Earlier objects in a
batch may already have emitted summaries when a later one fails, so a retry can
duplicate them. Lambda may retry once within the configured age; S3 has its own
delivery behavior. There is no partial-batch acknowledgement, dead-letter queue
or on-failure destination here. Events can be lost after retry/age exhaustion,
and throttling can delay processing. Before real use, add operational alarms and
a reviewed failure destination/replay procedure, and test these behaviors in an
authorized sandbox. This is unsuitable for a production alerting dependency.

## Offline validation that was executed

```powershell
.venv/Scripts/python tools/validate_iac.py
```

This runs `cfn-lint --config-file infra/cfnlintrc.json --template
infra/template.yaml --regions us-east-1` with
network socket connections and DNS resolution disabled. It supplies placeholder
AWS values and a workspace-local config so validation does not read an account
profile or discover credentials. The explicit cfn-lint config also disables its
usual user-config search. Installed/bundled schemas are used; schema
updates are not requested. See [verification.md](verification.md) and saved
[validation/checks.txt](validation/checks.txt). This is neither a live plan nor a
deployment test. SAM CLI is not required for this check and was not installed.

## Intended deployment steps: not executed

Only after separate parent authorization in a chosen AWS sandbox:

1. Review this template, its dependency licenses, costs and failure handling.
   Choose a region and a unique function name. The bucket name is fixed per
   account/region; repeated stacks would conflict and need a reviewed naming
   change. Use synthetic objects only.
2. Install/review the SAM CLI. Package the Python source under `src/`; the
   template's `CodeUri` points there. A future `sam build --template-file
   infra/template.yaml` uses the selected Python runtime. Docker is optional;
   no container workflow has been tested. Ensure the runtime SDK is suitable or
   deliberately package a pinned SDK and recheck licenses.
3. In that separately authorized environment, prepare a SAM deployment/change
   set, review transformed IAM/S3 invocation permissions and any artifact bucket,
   then explicitly approve execution. Deployment roles/artifact upload rights
   are separate from the function's runtime role. No deployment commands have
   been run or authorized by this project build.
4. Upload a copy of `samples/auth.jsonl` to a unique accepted `incoming/` key,
   inspect aggregate logs, and test size rejection, retries and duplicate events.
   Compare with the CLI; set a synthetic baseline if testing unusual sources.
5. Review retained resources, lifecycle timing, log retention and eventual
   cleanup. Removing a stack alone leaves its retained bucket and log group.

## Illustrative monthly costs, dated 2026-10-15

These are rough arithmetic assumptions for **us-east-1**, not fetched prices,
a quote, a real bill, or a free-tier promise. Recheck official regional pricing
before authorizing deployment. Ignore discounts/free tiers/tax. Assume 1,000
unique uploads/month at 100 KiB each, one 0.5-second 256 MB invocation and one GET
per upload, no retries/duplicates, seven-day object expiry, and 1 KiB of total
CloudWatch messages per invocation with fourteen-day retention. Actual platform
messages may be larger and retries multiply usage.

| Component | Assumed unit rate | Rough calculation |
| --- | --- | --- |
| S3 Standard storage | $0.023/GB-month | ~0.10 GB arrivals × 7/30 × rate = ~$0.00054 |
| S3 PUT | $0.005/1,000 | 1,000 = $0.005 |
| S3 GET | $0.0004/1,000 | 1,000 = $0.0004 |
| Lambda requests | $0.20/million | 1,000 = $0.0002 |
| Lambda compute (conservative assumed rate) | $0.000016667/GB-second | 1,000 × 0.5 × 0.25 = 125 GB-s = ~$0.0021 |
| CloudWatch ingestion | $0.50/GB | ~0.001 GB = ~$0.0005 |
| CloudWatch stored logs | $0.03/GB-month | ~0.001 × 14/30 × rate = ~$0.000014 |

Under those assumptions the modeled service usage is roughly **$0.01/month**.
This excludes deployment artifacts, optional alarms, failure destinations,
network egress, extra log messages, minimum billing details and other account
resources. IAM and the SAM transform introduce no modeled per-request charge.
SSE-S3 introduces no modeled KMS charge. There is no NAT gateway, provisioned
concurrency or LocalStack deployment in this design. Reserved concurrency is a
concurrency limit, not provisioned compute, and is not a spending cap.
