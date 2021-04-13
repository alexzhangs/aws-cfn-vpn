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
#?
#?   The STACKS option argument is a whitespace separated set of numbers and/or
#?   number ranges. Number ranges consist of a number, a dash ('-'), and a second
#?   number and select the stacks from the first number to the second, inclusive.
#?
#?   The number 0 is specially held for the manager stack, and the rest numbers
#?   started from 1 is for the node stacks.
#?
#?   The string `00` is specially held for a single stack that puts the manager
#?   and the node together.
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

function expansion () {
    #? Usage:
    #?   expansion <NUMBER|RANGE> [...]
    #? Option:
    #?   <NUMBER|RANGE>: a set of numbers and/or number ranges, the range's delimiter is dash `-`.
    #? Output:
    #?   The numbers listed in multi-line, sorted in ASC order, merged the duplicates.
    #?
    declare range
    for range in "$@"; do
        seq -s '\n' $(awk -F- '{print $1, $NF}' <<< "${range:?}")
    done | sort -n | uniq
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
        # sorting in DESC order, make sure the manager stack is processed at the last
        stacks=( $(expansion "${stacks[@]}" | sort -r) )
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
