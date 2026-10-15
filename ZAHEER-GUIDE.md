# Zaheer's walkthrough

Run the sample in the README first. It should show 13 rows, 12 unique events and
three findings. Exit 1 means the rules found alerts; it is easy to mistake that
for a broken program when calling the tool from another script.

## Follow a record through the code

`cli.py` chooses format/config. `io.py` opens a regular file, reads bounded UTF-8
lines and decodes JSONL/CSV. `Event.parse` in `core.py` checks each field. Naive
timestamps fail because two machines could disagree about when they happened.
Accepted times become UTC, and IP addresses get a canonical spelling.

`analyze` deduplicates and sorts events. The sample deliberately contains an
offset-equivalent duplicate and out-of-order rows. Sorting removes dependence on
export order; the tradeoff is bounded in-memory processing rather than an
unlimited stream. Exact duplicates can also hide genuine repeated attempts when
timestamp precision is too low. That limitation is documented, not solved.

Failures are grouped twice: source/user for bursts and source for sprays. Each
group moves a deque through time. New timestamp batches enter the right side;
events older than the inclusive left boundary leave. A counter tracks users still
in a spray window. When a user's last failure leaves, they stop contributing to
the distinct-user count. Grouping equal timestamps avoids intermediate counts
that depend on the order of simultaneous events.

Successful logins take a different path. A configured user's success from an IP
outside their explicit allowed list emits a first-occurrence finding. The tool
never decides the first observed source is trustworthy. Users missing from the
baseline are unassessed by that rule, which is a real coverage gap.

Finally, the CLI prints a summary or versioned JSON. Sorting report keys/findings
and leaving out the current time makes output reproducible. `samples/report.json`
was captured from the installed executable; a test compares current code against
it. Read `docs/schema.md` for the precise contract.

## Interview explanations

**Why Python and rules?** The standard library covers parsing, timestamps, IPs
and CLI arguments with zero runtime dependencies. Each rule has a concrete
trigger and explanation. This project has no trained model, evaluation dataset
or accuracy claim. ML would require representative data, labels, evaluation and
drift monitoring that are outside this small project.

**Burst versus spray?** Five failures for `mira` from one source can be a burst;
one failure for each of five users from one source can be a spray. Neither proves
an attacker is responsible. Shared NAT and a batch of expired passwords can
produce false positives. Changing thresholds needs evidence from authorized data.

**How do you handle bad data?** Reject the entire analysis with exit 2 and a safe
diagnostic. There is no silently skipped bad row or partial success. Limits apply
before deduplication so repeated rows cannot evade the event cap. Finding-cap
exhaustion also fails rather than hiding evidence in a truncated report.

**Why deduplicate?** Duplicate exports can inflate counts. Identity is UTC time,
user, canonical IP and outcome. Real attempts with identical fields/precision
also collapse, so future event IDs would be useful. Explain the tradeoff instead
of calling this universally correct.

**Complexity?** Sorting dominates at roughly O(n log n); grouping and moving
windows are linear in events plus findings. Event references, counters and
results use O(n + findings) memory within caps. This is design reasoning, not a
performance benchmark.

**What did tests prove?** Actual code was exercised for positives, negatives,
boundaries, timezones, malformed data, both formats, config and caps. Cloud tests
use fake clients/bodies and all tests block sockets. Ruff, strict mypy and offline
cfn-lint also run. `docs/verification.md` records results. None of these prove a
green remote workflow or successful AWS deployment.

## Explain AWS honestly

S3 holds objects and sends notifications. Lambda runs the same parser/rules per
object. CloudWatch gets bounded counts without usernames/IPs. IAM grants only
one input prefix and one log group's streams. The function has no S3 writes, so
it cannot trigger itself with output objects. SAM describes encryption,
retention and these resources.

Injected fetch/emit functions let tests exercise analysis and read bounds without
accounts or credentials. The AWS wrapper uses `GetObject` with an ETag condition,
reads at most cap+1 bytes and closes the response. Fixed errors prevent SDK
messages from disclosing object names. The entry point loads the SDK lazily.

Do not describe this as deployed, integration-tested, production-ready or
exactly-once. Notifications can duplicate or arrive out of order. There is no
durable idempotency store, cross-file state, failure destination or alarm. A
SHA-256 object identity helps downstream deduplication but prevents no duplicate
delivery. `docs/cloud.md` records those limits and cost assumptions, not a bill.

## Next work after review

Start with one authorized vendor-log converter and event IDs, preserving strict
malformed-input tests. Measure false positives before changing thresholds.
Consider incident grouping/cooldowns only after deciding what evidence they may
hide. For larger datasets, design sorted streaming or explicit state rather than
removing caps.

A separately authorized cloud sandbox could test deployment and transformed
permissions, recovery/alarms and durable idempotency. Those are future tasks.
Parent review controls publication; this build made local commits only.
Zaheer approved MIT for original code; third-party licenses stay separate.
