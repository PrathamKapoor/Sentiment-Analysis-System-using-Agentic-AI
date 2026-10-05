# Vercel deployment: frontend

The React/Vite single-page application can be hosted on Vercel. The Flask API,
PostgreSQL database, Redis, uploads, and generated reports remain separate
services. The repository's Docker Compose deployment is the supported complete
stack path; this Vercel setup deploys only `frontend/`.

## Configure the Vercel project

1. Import the repository into Vercel.
2. Set **Root Directory** to `frontend`.
3. Use the Vite framework preset. The build command is `npm run build`; the
   output directory is `dist`.
4. Configure `VITE_API_BASE_URL` for Production, Preview, and Development as
   the HTTPS base URL of the deployed API, including `/api/v1` (for example,
   `https://api.example.com/api/v1`). This is public frontend configuration,
   not a secret. Never put provider or database credentials in a `VITE_*`
   variable.
5. Configure the backend `CORS_ALLOWED_ORIGINS` with the exact production
   frontend origin. Preview deployments need an intentional allowlist policy;
   do not use a wildcard with credentialed requests.
6. Apply database migrations using the backend's one-shot migration workflow.
   The frontend does not run migrations or seed data.

`frontend/vercel.json` rewrites browser routes to the SPA entry point so direct
navigation and refreshes on React Router paths load the app.

## Runtime boundary

This repository's backend depends on PostgreSQL, Redis-backed revocation/rate
limits in production, local-or-configured file storage, synchronous report
generation, and a process-level serialized collection lock. Vercel currently
supports Flask through its Python runtime, packaging the Flask app as one
Function. Its function request and response body limit is 4.5 MiB, below this
backend's 25 MiB upload contract; its function filesystem is read-only except
for up to 500 MiB of `/tmp`; and each instance has its own process-local state.
Python functions can run longer on higher plans, but duration still has a plan
limit (30 minutes on Pro/Enterprise, with durations above 800 seconds in beta).
See the [Flask deployment guide](https://vercel.com/docs/frameworks/backend/flask),
[function limits](https://vercel.com/docs/functions/limitations),
[runtime filesystem behavior](https://vercel.com/docs/functions/runtimes), and
[duration configuration](https://vercel.com/docs/functions/configuring-functions/duration).

The current supported deployment therefore keeps Vercel on the Vite frontend
and runs Flask on a persistent backend host. This is a compatibility decision,
not a claim that Vercel cannot run Flask. A Vercel API deployment would need a
different upload path (such as direct-to-object-storage), externalized report
storage, a distributed collection lock/budget, and verified deployment entry
point and runtime behavior. None of those changes or a full-stack Vercel
deployment has been implemented or tested here.

No live Vercel deployment was performed as part of local repository work.
