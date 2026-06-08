# Security Requirements and Threat Model

## Security Requirements

- Authenticate every CDK request with a bearer API token.
- Store only SHA-256 token hashes in SQLite.
- Reject uploads without authentication.
- Accept only one `.py` file and an optional `requirements.txt`.
- Enforce upload size limits before writing temporary files.
- Store uploaded code, requirements, hashes, status, and verification results in the database.
- Run verification before returning a usable function URL.
- Fail closed when Bandit, Gemini, or ClamAV cannot complete.
- Keep the Gemini API key outside source control in `GEMINI_API_KEY`.
- Record authentication failures, upload events, verification outcomes, deletion, and invoke attempts in an audit trail.
- Preserve a JSONL audit hash chain so deleted or reordered records are detectable.
- Do not execute uploaded code in this server.

## Execution Boundary

This server does not run user code. The returned `/run/{function_id}` URL records an invoke attempt and returns `501`.

The separate Firecracker runner must provide the actual execution boundary:

- one function invocation per microVM or otherwise isolated execution context;
- no host directory mounts inside the guest;
- read-only code bundle device;
- no guest network by default;
- non-root handler process inside the guest;
- CPU, memory, file, process, open-file, and wall-clock limits;
- host-side timeout and VM termination;
- audit events for bundle creation, VM start, timeout, result parsing, and teardown;
- Firecracker jailer, seccomp, cgroups, and a hardened rootfs in production.

## STRIDE

| Category | Threat | Implemented mitigation | Open item |
| --- | --- | --- | --- |
| Spoofing | Attacker deploys as another user | Bearer token validation against hashed token records | Token rotation and scoped tokens |
| Spoofing | Forged invoke URL | Function IDs are UUIDs and list/delete require auth | Signed public invoke URLs if unauthenticated invokes are required |
| Tampering | Path traversal in upload filename | Filenames with path components are rejected | Support zipped bundles with traversal-safe unpacking |
| Tampering | Code changed after verification | Code and requirements are stored as blobs with SHA-256 hashes and audit records | Sign verified bundles before passing to Firecracker |
| Repudiation | User denies upload/delete/invoke attempt | SQLite audit rows and JSONL hash chain include actor, request ID, IP, event type, and outcome | Central append-only log storage |
| Information Disclosure | API token leakage through logs | Tokens are never logged and only hashes are stored | Secret scanning in CI |
| Information Disclosure | Uploaded code reads host secrets | This server does not execute code | Firecracker isolation must block host mounts and run as non-root |
| Denial of Service | Large uploads exhaust memory or disk | Server enforces byte limits for code and requirements | Per-user rate limits and quotas |
| Denial of Service | Slow scanner or LLM call blocks workers | Verifier is called synchronously and fails closed | Background job queue with bounded workers and timeouts |
| Elevation of Privilege | Uploaded code escapes process sandbox | No execution in this server | Firecracker jailer, seccomp, cgroups, hardened guest |

## Malicious Test Cases

- Upload a Python file using `os.system("rm -rf /")`; Bandit should reject it.
- Upload a fork bomb; Bandit or Gemini should reject it.
- Upload code that reads environment variables and sends them over the network; Gemini should reject it.
- Upload an EICAR string in `requirements.txt`; ClamAV should reject it when ClamAV is installed.
- Call `/functions` with no token or a wrong token; the server should return `401` and audit the failure.

## Review Notes

- The synchronous verification flow is simple and auditable, but it is not ideal for high throughput.
- Running `freshclam` on startup is optional because it may require network and host-level permissions.
- SQLite is acceptable for the requested scope; production should use a managed database with backups and row-level ownership checks.
