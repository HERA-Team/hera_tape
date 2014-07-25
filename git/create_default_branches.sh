#! /bin/bash
#
# create

_create_default_branches () {

    for branch in {dev,rev,prod}; do
        git checkout -b $branch
    done

}

_create_default_branches
