# Pilot browser checks

Run against a production web build with the test API URL baked in:

    KLAVE_LOAD_DOTENV=0 NEXT_PUBLIC_API_URL=http://127.0.0.1:18000 npm run build
    npm run test:e2e

The harness starts its own PostgreSQL container, API (:18000), and web
(:13000); it refuses occupied ports and never reuses a development service.
If Docker is unavailable locally, explicitly set PILOT_TEST_POSTGRES_URL
to the documented loopback test cluster. The harness creates and removes
only a uniquely named klave_pilot_* database there.

PILOT_TEST_STATE_DIR optionally selects an empty temporary state directory.
It contains synthetic credentials and must not be published. Traces,
video, and screenshots are disabled by default to keep tokens out of reports.
The core successful journey uses real services; interception is reserved
for deterministic error cases.
