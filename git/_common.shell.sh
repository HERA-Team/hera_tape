#! /bin/bash
# 
# dconover 2011

## dconover 2011
_filelock () {    ## temporary lock file to start processes

    local _usage=$FUNCNAME' tmp_file_name'

    # check for correct usage
    _fail_usage_args "$_usage" "$#" 1 "$1"

    local _tmp_file=$1

    if [ -d "$_tmp_file" ]; then 
        _fail_usage "Fail: $_tmp_file appears to be a directory, use a tmp filename instead" "$_usage"
        return $WRONG_ARGS
    fi

    # call with name of tmp file
    touch $_tmp_file.lock
    ln -n $_tmp_file.lock $_tmp_file 2>/dev/null
    
    if test $? != "0"; then
        # lock acquisition failed
        echo Fail: could not lock against $_tmp_file, try later
        rm $_tmp_file.lock
        return $BAD_LOCK
    fi

    rm $_tmp_file.lock
}

## dconover 2011
## deprecated by _fail_usage_args
## print a failure and usage message (optional) to stdout
_fail_usage () {
    local _usage_msg=$1
    local _fail_msg=${2:-"wrong number of args"}
 
    echo Fail: $_fail_msg >&2
    [ -n "$_usage_msg" ] && echo Usage: $_usage_msg >&2

    return $TRUE
}


## dconover 2011
_check_help () {    ## if the given variable is -h, print the usage
    local _usage=$FUNCNAME' "$_usage_msg" "$var1" || return $HELP'
    [ "$1" == "-h" ] && echo "Usage: $_usage" &&  return $HELP
    _fail_usage_args "$_usage" "$#" 2 || return $WRONG_ARGS

    local _usage_msg=$1
    local _var1=$2

    if [ "$_var1" == "-h" ]; then 
        echo "Usage: $_usage_msg" >&2
        return $HELP
    fi
}    

## dconover 2011
_fail_usage_args () {     ## print a failure and usage message (optional) to stdout
    local _usage=$FUNCNAME' $usage_msg "$#" $required_args_int[+|-] ["$failure_msg"] ["$1"]'
    [ "$1" == "-h" ] && echo "Usage: $_usage" &&  return $HELP  ## don't use _check_help since it call _fail_usage_args
    [ ! "$#" -ge 3 ] && _fail_usage "$_usage" && return $WRONG_ARGS 

    local _usage_msg=$1
    local _found_args=$2
    local _required_args=${3:-0}
    local _first_arg=$4
    local _return_msg=${5:-"wrong number of arguments"}
    
    [ "$_first_arg" == "-h" ] && echo "Usage: $_usage_msg" &&  return $HELP

    local _test='-eq'
    if [ "$_required_args" != "${_required_args%+}" ]; then
        _required_args=${_required_args%+}
        _test='-ge'
    elif [ "$_required_args" != "${_required_args%-}" ]; then
        _required_args=${_required_args%-}
        _test='-le'
    fi

    if [  ! "$_found_args" $_test $_required_args ]; then 
        echo Fail: "$_return_msg" >&2
        [ -n "$_usage_msg" ] && echo "Usage: $_usage_msg"  >&2
        return $FALSE
    fi

}

## dconover 2011
_last_file () {     ## most recent file matching given regex
    \ls -tr $1|tail -1
}

## dconover 2011
_broadcast_clean_exit () {     ## a sub to mail the admin of a script when it is killed

    local _usage='_broadcast_clean_exit $lockfile $abort_msg $email_sbj $email_add $err_log'
    [ "$1" == "-h" ] && echo "$_usage" >&2 && return $HELP

    local _lock_file=$1
    local _abort_message=$2
    local _email_subject=$3
    local _email_address=$4
    local _error_file=$5

    [ -f "$_lock_file" ] && rm $_lock_file
    echo Abort: $_abort_message

    cat $error_file|mailx -s "$_email_subject" $_email_address

    return $TRUE
}

## dconover 20111215 debug
_full_path () {     ## print the files full path if only a relative path is given
    local _usage=$FUNCNAME' $file_reference'
    _fail_usage_args "$_usage" "$#" 1 "$1"|| return $WRONG_ARGS

    local _dir=$1

    if [ "${1#/}" == "$1" ]; then echo $(pwd)/$1
    else echo $1; fi
}

## dconover 20111215 debug
_ps_grep () {
    local _usage=$FUNCNAME' $process_name'
    _fail_usage_args "$_usage" "$#" 1 "$1"|| return $WRONG_ARGS

    local _process=$1

    ps -o sess -C $_process|awk '
        $1!="SESS"{x[$1]++}
        END {
            for (n in x) out=sprintf("%s,%s",out,n)
            print substr(out,2)
        } 
    ' | xargs ps f -o pid,cmd -g
}

## dconover 2011
_ps () {     ## quick ps command to exclude noisy normal processes
    ps f -N -C imaplogin,couriertls,imapd,authdaemond,courierlogger,nfsd -g 1 -O sess
}

## dconover 20111214
_regex_replace_in_file () {

    local _usage=$FUNCNAME' $regex $file'
    _fail_usage_args "$_usage" "$#" 2 "$1"|| return $WRONG_ARGS

    local _regex=$1
    local _file=$2

    sed -e "$_regex" $_file $_file.tmp && mv $file.tmp $file

}

## dconover 20120111
_mailq () {     ## alias for mailq

    mailq -C /etc/mail/sendmail-gamma.cf

}

_fcd () {     ## "filepath" cd: change to the dirname of the given filepath (fcd /etc/fstab == cd /etc/)
 
    local _usage=$FUNCNAME' [-h] $file_path ## change to the dirname of the given filepath (fcd /etc/fstab == cd /etc/)'
    local _require=1

    _fail_usage_args "$_usage" "$#" $_require "$1" || return $WRONG_ARGS

    cd $(dirname $1)
}

_alias_exit () {    ## alias the exit command when to prevent accidental exit

    local _usage=$FUNCNAME' [-h] [$alias_msg]'
    local _require=1-

    _fail_usage_args "$_usage" "$#" $_require "$1"|| return $WRONG_ARGS

    local _msg="${1:-last exit on $(hostname -s)}"

    alias exit="echo $_msg"
}



