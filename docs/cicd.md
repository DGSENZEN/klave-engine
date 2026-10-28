# Continuous integration and production releases

GitHub Actions runs `Verify and deploy` on pull requests, pushes to `main`,
and manual dispatch. Verification includes Python tests, Ruff, mypy, browser
acceptance, client tests, lint, type checking, a synthetic engine evaluation,
production builds, and isolated container checks. Private gold drawings stay
on the operator's machine and are evaluated there before releases.

After verification succeeds on `main`, the deployment job uses the protected
`KLAVE_ENV` environment. Only `main` can access that environment. It stages
and checks a production Vercel build, deploys the exact verified API commit,
checks public API readiness, promotes the staged frontend, and checks the
public frontend. Main releases are serialized; production jobs are never
cancelled by a newer push. Pull requests never receive deployment secrets.
Vercel's separate Git integration may create previews, but its direct `main`
deployments are disabled in `apps/web/vercel.json` so it cannot publish a
frontend before the required checks and API release have completed.

## Manual API releases

GitHub's hosted runners cannot reach the server's SSH ingress, so the
deployment job runs with `EC2_DEPLOY_MODE=manual` unless the repository
variable says `ssh`. In manual mode it skips the SSH steps, records that in
the run summary, checks that the running API is ready, and promotes the
verified frontend. The frontend can therefore be ahead of the API: a frontend
change that needs a new endpoint must tolerate its absence until the API is
released.

To release the API, run the same steps from a machine that can reach SSH,
using the commit that passed verification on `main`:

```bash
sha=$(git rev-parse origin/main)
git archive --format=tar.gz -o "/tmp/klave-release-$sha.tar.gz" "$sha" \
  apps/api apps/__init__.py packages pyproject.toml uv.lock README.md \
  .dockerignore docker-compose.ec2.yml deploy
scp -i /path/to/klave-key.pem "/tmp/klave-release-$sha.tar.gz" "ubuntu@EC2_HOST:klave-release-$sha.tar.gz"
git show "$sha:deploy/ec2-release.sh" | ssh -i /path/to/klave-key.pem ubuntu@EC2_HOST \
  "bash -s -- '$sha' \"\$HOME/klave-release-$sha.tar.gz\""
curl --fail https://api.klave.space/ready
```

The script backs up, swaps the image, waits for readiness, and restores the
previous image if anything fails, exactly as it does from CI.

## Configuration

The existing `KLAVE_ENV` environment contains `VERCEL_TOKEN` and `EC2_SSH_KEY`.
Enter and rotate those values directly in GitHub. The workflow selects
the Vercel team and project through the protected environment variables
`VERCEL_ORG_ID` and `VERCEL_PROJECT_ID`, and uses Node.js 24. These identifiers
are not authentication credentials, but deployment targets belong in
environment configuration rather than hardcoded source.
Repository variables `EC2_HOST` and `EC2_KNOWN_HOSTS` select the existing API
host-key identity and pin its verified SSH public key. Deployment now routes
SSH/SCP through a fixed-port SSM tunnel, using short-lived GitHub OIDC credentials.
Set `AWS_REGION`, `AWS_ACCOUNT_ID`, `AWS_DEPLOY_ROLE_ARN` and `EC2_INSTANCE_ID`
in `KLAVE_ENV` only after reviewed provisioning. Authentication and the redacted
SSM/SSH preflight run before staging the frontend. Missing authorization fails
closed. Keep the PR unmerged while provisioning is blocked. See
[AWS setup](milestone-0-aws-setup.md) for exact trust, permissions and approval steps.
Host-key checking remains mandatory; never disable it to fix a connection.

The backend deployment keeps the server's `.env.prod`, database, drawings,
and existing Docker volumes. It builds images tagged with the commit SHA
while the previous API keeps serving, briefly stops API writes, creates a
verified backup, then starts the new API and waits for readiness. A backup
or startup failure restarts the previous API image and does not record the
candidate as successfully deployed. No volume deletion or automatic data
restore occurs. Destructive database migrations require a separately
reviewed compatibility and recovery procedure before release.

`deploy/ec2-release.sh COMMIT ARCHIVE` runs from SSH against the existing
`~/klave-engine` deployment. It records the successful revision in
`.release-current` on the server. To inspect production:

```bash
curl --fail https://api.klave.space/ready
curl --fail --head https://www.klave.space/bienvenida
gh run list --workflow release-check.yml --branch main
```

Keep at least the previous API image and matching verified backup until the
next release is accepted. Off-server backup copies and a complete restore
drill remain operational requirements; a passing CI run does not prove them.

Milestone 0 adds bounded, redacted SSH preflight and stages source under
`.releases/` before building. Accepted SHA directories are immutable; archive
extraction never overwrites legacy source or private configuration. Select the
accepted release's Compose file for subsequent operations. The mandatory
container stage includes actual backup creation and two fresh synthetic
restore/export drills. See [operator handoff](milestone-0-operations.md) and
the [gate record](pilot-release-record.md) for proof boundaries and pending work.
