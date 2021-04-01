#!/bin/bash

set -e -o pipefail

#? Description:
#?   Delete AWS CloudFormation stack(s).
#?
#? Usage:
#?   delete.sh [-r REGION] -x STACKS [...] [-p PROFILES ...] -d NAMES [...]
#?   delete.sh [-h]
#?
#? Options:
#?   [-r REGION]
#?
#?   The REGION specifies the AWS region name.
#?   Default is using the region in your AWS CLI profile.
#?
#?   -x STACKS [...]
#?
#?   The STACKS specifies the stacks index that will be operated on.
#?   The STACKS option argument is a whitespace separated set of numbers and/or
#?   number ranges. Number ranges consist of a number, a dash ('-'), and a second
#?   number and select the stacks from the first number to the second, inclusive.
#?
#?   Numbers or number ranges may be preceded by a dash, which selects all stacks
#?   from 0 to the last number.
#?   Numbers or number ranges may be followed by a dash, which selects all stacks
#?   from the last number to the last stacks.
#?
#?   The number 0 is specially held for the manager stack, and the rest numbers
#?   started from 1 is for the node stacks.
#?
#?   The node stacks are always being deleted before the manager stack.
#?
#?   [-p PROFILES ...]
#?
#?   The PROFILES specifies the AWS CLI profile that will be used for creating
#?   stacks.
#?   The STACKS option argument is a whitespace separated set of profile names.
#?   The order of the profile names matters.
#?
#?   -d NAMES [...]
#?
#?   The NAMES specifies the names of the stacks that will be deleted.
#?   The NAMES option argument is a whitespace separated set of stack names.
#?   The order of the stack names matters.
#?
#?   [-h]
#?
#?   This help.
#?
#? Example:
#?   delete.sh -x {0..3} -p profile-{0..3} -d vpn-{0..3}-sample
#?

function usage () {
    awk '/^#\?/ {sub("^[ ]*#\\?[ ]?", ""); print}' "$0" \
        | awk '{gsub(/^[^ ]+.*/, "\033[1m&\033[0m"); print}'
}

function expension () {
    awk -F- '{
        if (NF==1) {
            print $1, $1
        } else if (NF==2) {
            if ($1 == "") $1 = 0;
            if ($2 == "") system("usage");
            print $1, $2
        }}' <<< "${1:?}"
}

function delete-stack () {
    declare name=${1:?} profile=$2 region=$3

    if [[ -n $profile ]]; then
        xsh aws/cfg/activate "$profile"
    fi

    echo "deleting stack: $name ..."
    xsh aws/cfn/stack/delete -r "$region" -s "$name"
}

function main () {
    declare region stacks profiles names\
            OPTIND OPTARG opt

    xsh import /util/getopts/extra

    while getopts r:x:p:d:h opt; do
        case $opt in
            r)
                region=$OPTARG
                ;;
            x)
                x-util-getopts-extra "$@"
                stacks=( "${OPTARG[@]}" )
                ;;
            p)
                x-util-getopts-extra "$@"
                profiles=( "${OPTARG[@]}" )
                ;;
            d)
                x-util-getopts-extra "$@"
                names=( "${OPTARG[@]}" )
                ;;
            *)
                usage
                exit 255
                ;;
        esac
    done

    if [[ -z $stacks || -z $names ]]; then
        usage
        exit 255
    fi

    # build stack list
    if [[ $stacks == 00 ]]; then
        stacks=( $stacks )
    else
        stacks=(
            $(for item in $stacks; do
                  seq -s '\n' $(expension "$item");
              done | sort -nr | uniq)
        )
    fi

    # loop the list to delete stacks
    declare stack index
    for stack in ${stacks[@]}; do
        index=$(($stack))
        delete-stack "${names[index]}" "${profiles[index]}" "$region"
    done
}

declare BASE_DIR=$(cd "$(dirname "$0")"; pwd)

main "$@"

exit
