#! /bin/bash
# 
# update the origin to point to gitlabs
#
# dconover 20140724

_project_name () {
    local _project_name=${1:-${PWD##/root/git/}};

    if echo $_project_name | egrep -sq /; then
        _project_name=$(echo $_project_name|cut -d/ -f1);
    fi;

    echo $_project_name
}

## load shortcuts
source _common.shell.sh

alias=${1:-git-d}
dir=${2:-hpc}



## make sure we have everything
for b in {rev,dev}; do git checkout -b $b; done
git checkout prod

git remote rm origin
git remote add origin $alias:$dir/$(_project_name)
git push --all
