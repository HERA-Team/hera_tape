
_project_name ()
{
    local _project_name=${1:-${PWD##/root/git/}};

    if echo $_project_name | egrep -sq /; then
        _project_name=$(echo $_project_name|cut -d/ -f1);
    fi;

    echo $_project_name
}
