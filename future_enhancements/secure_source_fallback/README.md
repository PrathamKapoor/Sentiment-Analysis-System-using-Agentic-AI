# STATUS: EXPERIMENTAL
# NOT INTEGRATED INTO PRODUCTION APPLICATION

This isolated, offline prototype models a safe future fallback path when a requested source cannot be collected under its policy. It never bypasses the requested site, never discovers and calls arbitrary URLs, and does not change production routes, models, agents, migrations, or UI.

It uses a code-configured approved-source registry, deterministic intent extraction, capability-ranked registered adapters, bounded source/retry/time budgets, review normalization, and provenance that names the actual source. `NO_DATA_AVAILABLE` is a successful terminal outcome, never a reason to loop.

Credentials use AES-256-GCM with a fresh random 256-bit data key and nonce; the data key is wrapped using RSA-OAEP-SHA256 (3072-bit test keys). Associated data binds credential ID and source ID. `key_version` labels the wrapping key and deliberately remains outside associated data so rotation can rewrap the AES data key without re-encrypting plaintext. Python cannot guarantee zeroization of immutable plaintext strings; the prototype minimizes plaintext lifetime and never logs it.

Run independently:

```powershell
Set-Location future_enhancements\secure_source_fallback
python -m pytest -v
```

See [architecture.md](architecture.md), [threat_model.md](threat_model.md), and [integration_plan.md](integration_plan.md). Any promotion requires a separate approved security, migration, and CollectionService integration effort.
