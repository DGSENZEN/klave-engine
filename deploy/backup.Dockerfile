FROM postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
RUN apk add --no-cache python3
COPY deploy/backup.py /backup.py
COPY deploy/backup.sh /backup.sh
ENTRYPOINT ["/bin/sh", "/backup.sh"]
CMD ["daemon"]
