# Browser walkthrough report

## BW-001 — Duplicate account registration accepted

**Environment:** real manual browser; PostgreSQL-backed backend.

The public registration endpoint now canonicalizes email identity (trimmed,
lowercase), rejects an existing identity with `409 EMAIL_ALREADY_REGISTERED`,
and preserves the database unique constraint as the concurrent-request
integrity boundary. The registration transaction is rolled back on every
failure.

## BW-002 — Repeated unauthenticated `/auth/me` requests

The provider already avoids `/auth/me` when no access token is present. The
observed pair is consistent with a stale token and React development
StrictMode re-running the initial effect. The initial validation is now guarded
per provider mount; a 401 continues to clear invalid tokens through the
existing interceptor. The backend correctly continues to require JWT auth.

## BW-003 — Low contrast on registration/auth pages

The registration form inherited the dark auth background without its own
light foreground colors. It now has the same dark-panel visual language as the
login page, with explicit readable heading, label, input, validation and link
colors. Login already supplied readable panel colors; its relevant input
autocomplete attributes were added.

## Non-application console output

- React DevTools prompt: informational development output.
- React Router v7 future flags: P3 future-maintenance warnings; no routing
  defect was observed and no dependency upgrade was made.
- `chrome-extension://`, coupon collection, and BHK widget messages: external
  browser-extension noise, not application defects.

## BW-005 — Dataset upload permitted repeated submissions and showed no progress

The upload form now uses an in-flight guard, disables file/type controls, and
reports real Axios byte-upload progress. Identical same-project files are
blocked by server-computed SHA-256 checksum; a failed checksum match reuses the
failed dataset for retry rather than creating another row.

## BW-006 — `critic.csv` mapping failed with generic validation text

The reproduced root cause was the `grade` column's 0–100 critic scores being
mapped to the application Rating field, whose supported range is 0–5. ISO
dates and `publication → source` mapping were valid. Validation now reports the
specific field/row reason, preview exposes numeric min/max statistics, and the
UI warns before submission so Rating can be left unmapped or changed.
