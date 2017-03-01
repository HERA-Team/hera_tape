#!/bin/bash

# This script is run_backup.sh
# Script to automatically generate tape backups
# We run consecutive backups without user intervention until an error is raised
# or there are no more files to backup

# Usage:
# $ ./run_backup.sh
# Must be run in the /papertape/bin directory

# We have also defined "graceful exit" behavior for exiting out of the main loop
# without hard-coding situations that would normally lead to exit, such as no
# available files to add to tape or no available tapes to load in the mtx db.
# Pressing ctrl-C (or sending SIGINT from another terminal)  will wait for the
# current backup to finish, then exit the loop. There is currently no "resume"
# functionality to a given backup, and so halting a partially completed backup
# would require restarting entirely, including  adjusting several column values
# in the paperdata db.

# Note that ctrl-C will not immediately exit the backup process, and MUST wait for
# the process to finish. If for whatever reason the process must be killed
# immediately, one can use kill -9, or use ctrl-\ instead (to send SIGQUIT instead
# of SIGINT).

# Loop while backup script doesn't deliver errors
exit_status=0
not_caught=0
PID=

function clean_exit {
    echo -e "\ncaught SIGINT, waiting for current backup to finish before exiting..."
    not_caught=1
    if [ ! -z ${PID} ]; then
	wait $PID
	exit_status=$?
	echo "scipt exit status: $exit_status"
    fi
}

trap clean_exit SIGINT

while [ $exit_status -eq 0 ] && [ $not_caught -eq 0 ]; do
    ./papertape-cron.sh &
    PID=$!
    wait $PID
    exit_status=$?
    if [ $exit_status -ne 0 ]; then
	echo Exited with $exit_status
    fi
done