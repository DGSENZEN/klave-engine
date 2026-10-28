# Separate operator image: no API/database credentials or drawing data mount.
FROM postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
RUN apk add --no-cache python3 aws-cli
WORKDIR /ops
COPY deploy/backup.py deploy/s3_backup.py deploy/backup_monitor.py /ops/deploy/
ENV PYTHONUNBUFFERED=1 TMPDIR=/scratch AWS_PAGER="" AWS_DEFAULT_REGION=us-east-2
ENTRYPOINT ["python3", "/ops/deploy/backup_monitor.py"]
