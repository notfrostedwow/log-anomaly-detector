# Security and responsible reporting

This bounded offline demonstration is not an access-control system or production
monitoring service. Findings require human review. The undeployed cloud adapter
has offline unit coverage only.

CLI files/config are untrusted. Strict UTF-8 JSONL/CSV parsing, exact fields,
timezone-aware dates and file/line/event/finding caps constrain processing.
Malformed input fails the whole analysis. There is no `eval`, pickle, archive
extraction, dynamic plugin or executable template. The CLI never imports an SDK
or reads credentials. Network-capable code exists only in the optional Lambda
entry point, which local validation never invokes against AWS.

Input/config must be regular local files. Links/reparse points (including
parents), devices, directories and pipes fail. Windows UNC/device paths and
alternate streams fail. Opening checks file identity and uses no-follow and
nonblocking flags where available. This is best-effort path hardening, not a
sandbox: a hostile local process can still race parent-directory changes,
especially on Windows. Use a trusted directory and OS access controls. The CLI
can read explicitly supplied authorized local files outside a repository; this
development session itself stays in the project workspace.

Only stdout/stderr are written. Narrow ASCII usernames and validated IPs/dates
prevent terminal escape injection into readable reports. Errors avoid echoing
raw records, paths or arguments. Full CLI findings contain user/IP values by
design; reports from authorized real data would be sensitive. Included fixtures
are entirely synthetic; no real-log retention policy is implied.

The adapter validates event/bucket/key/ETag/size, uses conditional bounded reads,
and outputs aggregate counts without raw log values. Its runtime role grants no
S3 writes and scopes reads/logs to one prefix/group. The template specifies
public-access blocking, encryption, TLS and retention. [docs/cloud.md](docs/cloud.md)
covers duplicate delivery, failure/retry limits, retained resources and missing
production controls. No independent security audit/certification is claimed.

Report suspected vulnerabilities privately to the parent/repository owner using
an already established private channel. No advisory/contact address has been
configured; do not invent one or disclose sensitive details in public issues.
Include the tool version, a minimal **synthetic** reproducer, expected/actual
behavior and the affected boundary. Never send credentials, private logs or an
exploit targeting a live system. No response-time or bug-bounty promise is made.

Run `.venv/Scripts/python tools/verify.py` and inspect saved outputs before
review. Tests/static checks reduce mistakes; they are not a security audit.
Only 0.1.x is currently developed; no long-term support policy is established.
