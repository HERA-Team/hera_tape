#!/bin/sh
# 
# create a repo
#
# dconover


repo=$1

token=put_your_api_token_here



test -z $repo_name && echo "Repo name required." 1>&2 && exit 1



curl -H "Content-Type:application/json" https://gitlab.com/api/v3/projects?private_token=$token -d "{ \"name\": \"$repo\" }"
