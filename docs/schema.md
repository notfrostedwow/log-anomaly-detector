# Data and report contracts

## Physical input

Use a local regular UTF-8 file without a BOM, with `--format jsonl` or `--format
csv`. LF, CRLF and a missing final newline are supported. No blank records,
comments, archives or multiline CSV records. Caps include duplicate events and
line-ending bytes. CSV's header counts against file bytes but not event count.
Malformed input rejects the whole analysis, with a physical line number where
possible and no echoed raw values. JSON duplicate keys/non-finite numbers fail.

JSONL has one complete object per physical line. CSV's header names each of the
four fields exactly once, in any order, case-sensitive and without extra spaces:

```csv
timestamp,user,source_ip,outcome
2026-01-01T00:00:00Z,mira,192.0.2.44,failure
```

Single-physical-row CSV quoting is supported. Empty JSONL and header-only CSV
yield empty reports with null start/end. Completely empty CSV fails: no header.

| Field | Accepted value |
| --- | --- |
| `timestamp` | String `YYYY-MM-DDTHH:MM:SS[.ffffff](Z or ±HH:MM)`, valid calendar date, 1–6 optional fractional digits and explicit offset |
| `user` | 1–64 ASCII characters; start with a letter, then letters, digits, `_`, `.` or `-` |
| `source_ip` | IPv4/IPv6 string, without zone/scope ID, hostname, port, subnet or whitespace |
| `outcome` | Exactly the string `failure` or `success` |

`T`/`Z` must be uppercase. Offset hours are 00–23 and minutes 00–59 (less than
24 hours total). Seconds are 00–59; leap seconds/extra fractional precision fail.
UTC conversion must stay within years 1–9999. There is no local-time/DST inference.
`-00:00` is treated as zero offset, not an unknown timezone marker. Output has six
fractional digits and `Z`. Users are case-sensitive. IPs use Python `ipaddress`
canonical spelling; plain IPv4 and IPv4-mapped IPv6 remain distinct identities.

The parser accepts any valid IP. Repository fixtures use documentation ranges
`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `2001:db8::/32` only. There
are no live lookups.

## Ordering, duplicates and windows

Validated events are collected within the cap, normalized to UTC and sorted by
`(timestamp, user, canonical source_ip, outcome)`. Exact duplicates of that tuple
collapse regardless of offset/IP spelling or row order. There is no event-ID or
fuzzy deduplication. Failure and success at the same time are distinct. Genuine
attempts at identical timestamp precision can collapse; the duplicate count makes
this decision visible. Deduplication is per invocation, not persistent.

Each failure group examines every distinct failure timestamp `t`. Its window is
`[t - window_seconds, t]`, both ends inclusive, including all events at `t`
together. Near year 1, clamp the left boundary to the minimum supported UTC date.
An event exactly 300 seconds old is included in a 300-second window; one
300.000001 seconds old is excluded. Successes neither count nor reset failures.

Bursts group by `(source_ip, user)` and count failed events. Sprays group by
`source_ip` and count distinct users with failures still in the window. Repeated
failures for a user add only one spray user. Each qualifying group/endpoint emits
once, including overlapping windows. Equal-time batches emit once per group, not
once per row. No cooldown, suppression or incident aggregation is implied.

Unusual-source checks assess only successes for explicitly baseline-listed users.
An unknown exact source yields one finding for the first success per `(user,
source_ip)` in the entire analyzed input. Start/end are that first event's time;
count is **1**, not the number of later successes. Allowed successes and users
absent from the baseline yield none. A missing/empty top-level baseline disables
the rule; an empty IP list for one user fails config validation. Baselines are
independently supplied, never inferred from the analyzed input. No CIDR support.

## Report version 1.0

The executable example is [samples/report.json](../samples/report.json). The
offline [JSON Schema](report-schema.json), with no remote references, is tested
against the actual sample and an empty report. Runtime validation uses code and
needs no JSON-schema dependency.

| Field | Meaning |
| --- | --- |
| `schema_version` | Exactly `1.0` |
| `tool_version` | Package version that generated the report |
| `settings` | Effective numeric thresholds and bounds |
| `baseline` | Mode and configured user count; allowed IP values omitted |
| `input` | Physical event rows, unique count, duplicates removed, UTC min/max or null |
| `finding_count` | Exactly the length of `findings` |
| `findings` | Ordered complete findings, no silent truncation |

Each finding has `rule`, `source_ip`, `user` (null for spray), `window_start`,
`window_end`, `count`, `explanation`. Count means failed events for bursts,
distinct users for sprays, and 1 for unusual sources. Burst/spray start is the
theoretical left boundary, not necessarily a matching event time.

Findings sort by `(window_end, rule, source_ip, user-or-empty-string)` with lexical
IP ordering. JSON keys sort alphabetically, text is ASCII-escaped, indentation is
two spaces and output ends with a newline. No wall-clock generation time, random
ID, input path or input-order metadata is included. The same normalized event
multiset and config produce identical bytes on the supported runtime. Preserve
baseline values separately: reports omit them.

Consumers should reject unsupported `schema_version` values. Changes to required
fields, ordering or field meanings require a new schema version. Explanation
wording may change with tool versions. The cloud summary has a separate shape
described in [cloud.md](cloud.md).

Input/config validation and read errors occur before stdout output, with a safe
stderr diagnostic and exit 2. An output-stream failure can leave partial bytes;
consumers must check exit status before accepting a report. A cap failure never
labels partial analysis as complete.
