# M0 AWS deployment and off-host backup setup

These templates prepare a separate infrastructure review. They do not authorize IAM changes, production deployment, backup transfer, or restore. Keep the M0 PR unmerged until the deployment role is provisioned and its environment variables are configured: main deployments deliberately fail closed when SSM/OIDC is unavailable. There is no public SSH fallback.

## Deployment identity and tunnel

`deploy/aws/github-deploy.json` creates a GitHub OIDC provider, the `klave-github-deploy` role, and `Klave-DeploymentSSH`, a Session Manager document fixed to port 22 with no configurable ports or interactive SSM shell. StartSession is limited to one instance and that document. The GitHub trust requires exact audience `sts.amazonaws.com` and the repository's verified subject ending `:environment:KLAVE_ENV`. Check `GET /repos/OWNER/REPO/actions/oidc/customization/sub`; recently created repositories use immutable owner/repository IDs. Do not guess the subject from the repository's display name.

The deployment environment must allow only the `main` branch. Pull requests receive no AWS OIDC permission. The deployment job assumes the one-hour role, installs the official Session Manager plugin from a versioned HTTPS URL with its pinned SHA256, and authenticates SSH inside the SSM TLS tunnel. Existing SSH private-key authentication and strict trusted-host verification remain required. No EC2 ingress rule changes are needed. `EC2_HOST` is the host-key identity inside the tunnel; routing uses `EC2_INSTANCE_ID`.

The role has no Run Command, S3, IAM administration, or interactive-session permission. `ssmmessages:OpenDataChannel` uses resource `*` because the message gateway does not support resource-level ARNs; opening a channel still requires the session token issued by the allowed StartSession call. Termination requires both the target instance and the caller's own AWS session identity tags. SSH tunnel traffic is not command-logged by Session Manager; record GitHub deployment logs and release/image identities privately.

If an organization SCP explicitly denies OIDC operations, stop provisioning this template and obtain the organization administrator's approved resolution. Do not replace it with permanent AWS keys, change roles to evade the restriction, loosen trust to all repositories, or widen SSH ingress. An account administrator's Allow cannot override an organization Deny. Also inspect existing provider configuration before creating one; do not blindly replace a shared provider.

After approved provisioning, set these non-secret `KLAVE_ENV` variables from the actual outputs:

- `AWS_REGION`
- `AWS_ACCOUNT_ID`
- `AWS_DEPLOY_ROLE_ARN`
- `EC2_INSTANCE_ID`

Retain the existing `EC2_HOST`, `EC2_KNOWN_HOSTS` and private `EC2_SSH_KEY`. Verify the host fingerprint out of band. A successful browser SSM session alone does not prove GitHub OIDC or the SSH key. A successful main workflow is required for G3; do not count policy simulation as live deployment evidence.

## Backup resources and permissions

`deploy/aws/backups.json` creates a private S3 bucket with all public-access blocks, bucket-owner-enforced ownership, versioning, and AES256 server-side encryption using S3-managed keys. Its policy denies non-TLS access and uploads without explicit AES256. The bucket and its contents are retained on stack deletion. There is no automatic expiration: establish retention only after a separately recorded successful application restore. Encryption-key management and recovery are handled by S3; access recovery still requires a separately available authorized AWS operator.

A policy on the existing instance role allows only PutObject/GetObject/GetObjectVersion under this bucket's `backups/` prefix and PutMetricData in namespace `Klave/M0`. It grants no delete, bucket administration, IAM, cross-account, or SNS publishing permissions. The deployment role cannot read backups.

The SNS email endpoint is a `NoEcho` template parameter. Keep the supplied address and resource parameters out of the public repository and PR. The recipient must confirm the AWS SNS subscription. The topic permits the specific CloudWatch alarm in this account to publish generic operational messages. Do not put filenames, customer details, credentials, or dump contents in alerts.

AWS storage, metric/alarm and notification charges are usage-based. Record current archive sizes and review current AWS regional pricing before approval. Versioned copies accumulate; never configure automatic deletion to enforce a budget before a recovery/retention decision.

## Install and verify after approval

First review a CloudFormation change set for the backup template, parameters, and IAM policy, then obtain approval to execute it and transfer existing private database/drawing backups into the named bucket. Creating a change set does not grant these permissions; executing it does.

Build the dedicated operations image from the reviewed commit on the server:

```bash
sudo docker build -f deploy/backup-ops.Dockerfile -t klave-backup-ops:REVIEWED_SHA .
sudo docker image inspect --format '{{.Id}}' klave-backup-ops:REVIEWED_SHA
```

Prepare a private file containing only the actual `AWS_REGION`, `KLAVE_BACKUP_BUCKET`, and `EC2_INSTANCE_ID` as unquoted `KEY=value` lines. Pass it and the exact `sha256:` image ID to:

```bash
bash deploy/install-backup-ops.sh /private/path/backup-ops.env sha256:EXACT_IMAGE_ID
```

The operator container uses host networking for IMDSv2 credentials with metadata response hop limit **1**. Verify the instance actually has hop limit 1 before granting backup access; retain IMDSv2-required. The API containers must not gain access to instance credentials. This operations image mounts only completed local backups read-only plus private operator state/scratch, drops capabilities, and uses a read-only root filesystem. It receives no production database password or API data volume. The image includes PostgreSQL 16 archive tools and AWS CLI; no application dependencies change.

The hourly timer copies all new complete snapshots in chronological order, including intermediate pre-upgrade snapshots, each to a fresh immutable object prefix, pins each downloaded object version, checks encryption/versioning, fetches every archive back, verifies bytes/archive integrity with the real backup verifier, and publishes COMPLETE only after verification. State advances atomically after the marker is also fetched back. Source snapshot age and fetch-back age must both be at most 36 hours; re-uploading an old snapshot cannot reset freshness. A failed copy retains the previous state and leaves incomplete remote prefixes for investigation.

Before any transfer, the fetch-back filesystem must have space for every archive plus 2 GiB reserve and sufficient inodes; rejection preserves the last success. Each run reports `OffsiteBackupHealthy` as 1 only when the verified snapshot is current and local backup storage has at least 2 GiB and 5% inode headroom. Otherwise it reports 0. A separate CloudWatch alarm treats missing hourly reports as failures, so stopping the timer or losing the server still alerts. Two consecutive hourly breaching/missing periods trigger the alarm; alarm recovery also notifies. Copying unchanged snapshots does not reset their age.

Privately inspect the first state record, actual S3 object version IDs/encryption, service exit status and CloudWatch metric/alarm. Confirm SNS delivery by a recorded controlled alarm test; a publish response is not evidence the human received it. Keep delivered-alert evidence PENDING until the recipient confirms receipt. If metric publishing itself fails, the missing-data alarm must notify after its evaluation window.

To disable a failed rollout, stop/disable only `klave-offsite-backup.timer` and its operator service. Preserve state, local backup volumes, images and remote copies for diagnosis. Never prune Docker or delete backup objects as cleanup.

Fetch-back integrity is not application recovery. G5 still requires a restore into fresh isolated private resources using matching release/images, application/account/isolation checks, and independently reviewed drawing/export expectations. Do not point tests at live volumes or restore over production.

## References

- [GitHub AWS OIDC and immutable subject formats](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
- [SSH and SCP through Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-enable-ssh-connections.html)
- [Session ownership and target tag conditions](https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-restrict-access-examples.html)
- [Message gateway resource limitations](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ssmmessages.html)
