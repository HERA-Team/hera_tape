
_nc_local () {
    local _dir=${1:-/dev/shm}
    local _port=${2:-7001}

    ( cd $_dir; nc -l $_port|tar x)
}

_nc_remote () {
    local _dir=${1:-test.dat}
    local _work_path==${2:-/papertape}
    local _remote_host=${3:-shredder}
    lcoal _local_host=${4:-orochi.sas.upenn.edu}
    local _port=${5:-7001}

    ssh $_remote_host "( cd $_work_path; tar c $_dir|nc $_local_host $_port)"
}

