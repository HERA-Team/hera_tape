

_p () { python -c "$1"; }
_r () { rm -r /papertape/shm/*; ssh shredder 'mysql paperdatatest <x; mysql mtx <y'; }
_t () { (date; echo ${1:-$tlast}; time python ${1:-$tlast}; date;) >t.err.$! 2>&1; cat t.err.$!; tlast=${1:-$tlast}; }
_v () { vim ${1:-$last};last=${1-$last}; }
_m () { echo using file: ${2:-$mlast}; echo "$1"| mysql --defaults-extra-file=/root/.my.${2:-$mlast}.cnf||ls /root/.my.*; mlast=${2:-$mlast}; }
