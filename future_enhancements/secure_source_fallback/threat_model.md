# Threat model

| Threat | Impact | Current mitigation | Residual risk | Future production recommendation |
|---|---|---|---|---|
| API credential theft | Unauthorized provider use | AES-256-GCM envelope encryption; no plaintext serialization/logging | Private-key compromise still exposes wrapped keys | Use KMS/HSM and access auditing |
| Database compromise | Ciphertext exfiltration | Keys are separately wrapped; AAD binds identity | Offline brute force/keys remain a concern | Separate DB and key-management access |
| RSA private-key compromise | Credential decryption | Ephemeral in-memory test keys only | Full compromise of records for that key | KMS, rotation, break-glass controls |
| Ciphertext tampering | Credential substitution | GCM authentication and OAEP | Denial of service possible | Alert on decrypt failures |
| Source impersonation | Untrusted data | Static approved registry and registered adapters | Registry governance is manual | Formal approval/change review |
| Malicious API response | Poisoned/malformed records | Typed adapters, payload cap, normalization | Semantic quality cannot be fully proven | Schema validation, reputation checks |
| Malicious catalog listing | SSRF/unapproved source | Catalogs never execute or register endpoints | Human research error | Independent legal/security review |
| SSRF/DNS rebinding/redirect to private target | Internal network access | Intent parser rejects IP private ranges; no network adapter exists | Production adapters need connect-time checks | Reuse CollectionService SSRF validation on every hop |
| Fallback loop/retry exhaustion | DoS | One resolver pass and central bounded budgets | Slow in-process work can consume budget | Request timeout/circuit breaker |
| Rate-limit exhaustion | Provider account degradation | Bounded retries and terminal rate-limit outcome | No cross-request quota in prototype | Per-source durable quotas |
| Provenance confusion | Misrepresented source | Actual source and attempt outcomes are explicit | UI could still mislabel it | Render provenance prominently |
| Prompt injection | Agent/control compromise | Text remains normalized data, no model/tool execution | Future LLM integration changes threat | Strict trusted/untrusted prompt boundary |
| Secret logging | Credential exposure | Public DTO omits plaintext; generic errors | Third-party libraries may log | Redaction filters and logging review |
| Path traversal | File compromise | No file input/output paths | Future fixtures/storage may add paths | Canonical paths and allow-lists |
| Credential downgrade/fallback abuse | Weaker source selected | Capability matching, allow-list, credential-required terminal state | Priority governance is manual | Policy review and source risk tiers |
| Malicious URL slug | Injection or memory abuse | Decode, control-character rejection, 512-char cap | Entity extraction is heuristic | Formal URL/parser tests |
| Dependency compromise | Code execution | Small dependency set; cryptography only | Dependency supply-chain risk | Pin hashes, SBOM, vulnerability scanning |
