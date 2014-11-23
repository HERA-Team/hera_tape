
## open a a log and send all output to that log
## close the logfile
## or kill the logfile; print it's contents; remove the evidence
_logfile () {    ## open, close, or kill the logfile
    local action=$1
    local log=$2

    case $action in
        open)
            exec 6>&1
            exec 1>$log 2>&1
        ;;
        close)
            exec 1>&6 6>&-
        ;;
        kill)
            exec 1>&6 6>&-
            cat $log && rm $log
        ;;
        tty)
            exec >/dev/tty 2>&1
            cat $log
            echo $log
        ;;
    esac
}


export LOG_DIR=/root/git/papertape.shredder/bin/log TERM=ansi
#alias pylint='pylint --rcfile=~/.pylint.d/pylintrc'

pylint () { /root/.pyenv/shims/pylint --rcfile=~/.pylint.d/pylintrc $1; }

_l () { TLAST=${1:-TLAST}; pylint $TLAST; cat pylint_${TLAST%.py}.txt; }
_p () { python -c "$1"; }
_r () { rm -r /papertape/shm/*; ssh shredder 'mysql paperdatatest <x; mysql mtx <y'; }
_t (){
    
    local log_file=$LOG_DIR/t.err.$RANDOM
    _logfile open $log_file

    date
    echo ${1:-$TLAST}
    time python ${1:-$TLAST}
    date

    _logfile tty $log_file
    TLAST=${1:-$TLAST}
}
_v () { vim ${1:-$last};last=${1-$last}; }
_m () { echo using file: ${2:-$mlast}; echo "$1"| mysql --defaults-extra-file=/root/.my.${2:-$mlast}.cnf||ls /root/.my.*; mlast=${2:-$mlast}; }
