#! /bin/bash
#
# run and schedule new dump
#
# dconover 20150301

source common.sh

dump_script=/root/git/papertape.dconover/bin/papertape-prod_dump.py
process_file=/var/run/papertape.pid
log_file=/papertape/log/papertape.log.$$.$(date +%Y%m%d-%H%M)
log_link=/papertape/log/papertape.log
override_file=/var/run/papertape.override

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

## run dump
echo starting papertape dump: $(date)
time python $dump_script || (
    echo Fail: bad exit from $dump_script $?
    _logfile close
    exit $DUMP_FAILURE
)

## schedule next run
echo $0|at now +10min

## unlock process file
rm $process_file
echo ending papertape dump: $(date)

_logfile close 


