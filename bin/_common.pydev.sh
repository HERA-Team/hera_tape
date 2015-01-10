
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

_pgrep () { grep "$*" paper_*.py; }
_highlight () { highlight -A $1; }
_pylint () { /root/.pyenv/shims/pylint --rcfile=~/.pylint.d/pylintrc $1; }

_l () { TLAST=${1:-TLAST}; _pylint $TLAST; cat pylint_${TLAST%.py}.txt; }
_p () { python -c "$1"; }
_r () { rm -r /papertape/shm/*; ssh shredder 'mysql paperdatatest <x; mysql mtx <y'; }

_date () {
    date +%Y%m%d-%H%M
}
_t (){
    
    local _pid=$RANDOM
    local _log_file=$LOG_DIR/t.err.$_pid

    echo opening $_log_file
    _logfile open $_log_file
    [ -f "/root/git/papertape.shredder/bin/x.log" ] && rm x.log
    ln -s $_log_file /root/git/papertape.shredder/bin/x.log

    local _command=${1:-$TLAST}
    local _comment=${2}

    echo _t:$(_date):$_command${_comment:+:$_comment}
    if [ -n "$_command" ]; then 
        time python $_command
    else
        echo empty command: "'$_command'"
    fi
    echo _t:$(_date)

    _logfile tty $_log_file
    export TLAST=$_command
}
_v () { vim ${1:-$last};last=${1-$last}; }
_m () { echo using file: ${2:-$mlast}; echo "$1"| mysql --defaults-extra-file=/root/.my.${2:-$mlast}.cnf||ls /root/.my.*; mlast=${2:-$mlast}; }
_dd () {  dd if=/dev/nst0 bs=32k count=1 conv=sync,block; }
_rewi () { mt -f /dev/nst0 rewi; }
_fsf () { mt -f /dev/nst0 fsf $1; }
_tf () { tar tf /dev/nst0 ; }

_comment () { sed -e 's/^/# /'; }

_pc () {    ## list classes in a module
    local _module=$1
    local _list=${_module:-$(ls paper_*.py)}
    for _module in $_list; do
        echo $_module:
        _inspect="import ${_module%.py}, sys, inspect\nfor x in inspect.getmembers(${_module%.py}, inspect.isclass):\n  print('    ', x)"
       echo -e "$_inspect"|python|grep ${_module%.py}; echo 
    done
}

_pi () {   ## inpsect fucntion source code (takes: _module, _class, _function)
    local _module=$1
    local _class=$2
    local _function=${3:-__init__}
    cat <<eop|sed -e 's/        //'|python|highlight -AS py
        import $_module, inspect
        print(''.join(inspect.getsourcelines($_module${_class:+.$_class}.$_function)[0]))
eop
}

_pm () {    ## inspect class and list all methods

    local _module=$1
    local _class=$2
    
    cat <<eop|sed -e 's/        //' | python | highlight -AS py
        import $_module, inspect
        for function in inspect.getmembers($_module.$_class, predicate=inspect.isfunction):
            print(function)
eop
}


