#! /bin/bash
#
# run and schedule new dump
#
# dconover 20150301

source common.sh

dump_script=papertape-prod_dump.py
process_file=/var/run/papertape.pid
log_file=/papertape/log/papertape.log.$$.$(date +%Y%m%d-%H%M)
log_link=/papertape/log/papertape.log
override_file=/var/run/papertape.override

DUMP_SUCCESS=0
DUMP_OVERRIDE=1
DUMP_FAILURE=2
DUMP_FINISH=3

_logfile open $log_file

## check override file
if [ -f "$override_file" ]; then 
    echo Abort: found $override_file
    _logfile close 
    exit $DUMP_OVERRIDE
fi

## debug override_file
touch $override_file

## log link 
[ -f "$log_link" ] && rm $log_link
ln -s $log_file $log_link

## lock process file and record current pid
_filelock $process_file
echo $$ >>$process_file

## start a timer
STARTTIME=$(date +%s)

## run dump
echo starting papertape dump: $(date)
time python3 $dump_script || (
    echo Fail: bad exit from $dump_script $?
    _logfile close
    exit $DUMP_FAILURE
)

## get the elapsed time
ENDTIME=$(date +%s)

## schedule next run
#echo $0|at now +10min

## unlock process file
rm $process_file
echo ending papertape dump: $(date)

_logfile close 

## if we didn't actually tape anything, the time difference will be small
if [ $(($ENDTIME - $STARTTIME)) < 120 ]; then
    echo "No more files to tape"
    exit $DUMP_FINISH
else
    # remove override file
    rm $override_file
    exit $DUMP_SUCCESS
fi