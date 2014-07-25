#! /bin/bash
#
# a script to change the remote
# 
# dconover 20140725

REPO_HOST=pez
REPO_PATH=git-repo

_project_name ()
{
    local _project_name=${1:-${PWD##/root/git/}};

    if echo $_project_name | egrep -sq /; then
        _project_name=$(echo $_project_name|cut -d/ -f1);
    fi;

    echo $_project_name
}

_create_default_branches () {

    for branch in {dev,rev,prod}; do
        git checkout -b $branch
    done
}

_update_remote_repo () {
  
    local _usage=$FUNCNAME' [-h] [$new_project_name]  ## execute: git remote rm origin && git remote add origin $REPO_HOST:$REPO_PATH/${1:-${PWD##/root/git/}}.git'

    ## one variable must be passed
    local _require=1-

    ## check if the number of variables matches $_require 
    _fail_usage_args "$_usage" "$#" $_require "$1"|| return $WRONG_ARGS

    local _project_name=$(_project_name)
    local _repo_dir=$REPO_PATH/$_project_name.git

    ssh $REPO_HOST git init --bare $_repo_dir &&
    git remote rm origin &&
    git remote add origin pez:$_repo_dir
}

work=/root/git/$(_project_name)
source $work/git/_common.shell.sh || exit 

_update_remote_repo $*

