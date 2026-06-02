# Lab 6 - Secure Deployment Environment - Student 1
# Runs the audit tool inside Debian 13 "Trixie".
FROM debian:trixie-slim

# Packages the script needs in the slim base image:
#   procps -> ps,  mawk -> awk,  hostname,  rsyslog -> config for the logging check
RUN apt-get update \
 && apt-get install -y --no-install-recommends procps mawk hostname rsyslog \
 && rm -rf /var/lib/apt/lists/*

COPY linux_review_student1.sh /audit/linux_review_student1.sh
RUN chmod +x /audit/linux_review_student1.sh

ENTRYPOINT ["/audit/linux_review_student1.sh"]
