

log_dir=/root/git/papertape/bin/log

_p () { python -c "$1"; }
_r () { rm -r /papertape/shm/*; ssh shredder 'mysql paperdatatest <x; mysql mtx <y'; }
_t () { echo >/dev/null; (date; echo ${1:-$tlast}; time python ${1:-$tlast}; date;) >$log_dir/t.err.$! 2>&1; cat t.err.$!; echo $log_dir/t.err.$!; tlast=${1:-$tlast}; }
_v () { vim ${1:-$last};last=${1-$last}; }
_m () { echo using file: ${2:-$mlast}; echo "$1"| mysql --defaults-extra-file=/root/.my.${2:-$mlast}.cnf||ls /root/.my.*; mlast=${2:-$mlast}; }
