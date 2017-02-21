#!/bin/bash

# This script is run_backup.sh
# Script to automatically generate tape backups
# We run consecutive backups without user intervention until an error is raised
# or there are no more files to backup

# Loop while backup script doesn't deliver errors
exit_status=0

while [ $exit_status -eq 0 ]; do
    ./papertape-cron.sh
    exit_status=$?
    if [ $exit_status -ne 0 ]; then
	echo Exited with $exit_status
    fi
done