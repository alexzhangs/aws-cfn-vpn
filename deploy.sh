#!/bin/bash

set -e -o pipefail

#? Description:
#?   Deploy AWS CloudFormation stack(s) from the template and the config files.
#?
#? Usage:
#?   deploy.sh [-r REGION] [-x STACKS ...] [-p PROFILES ...] [-u NAMES ...] -c CONFS [...]
#?   deploy.sh [-h]
#?
#? Options:
#?   [-r REGION]
#?
#?   The REGION specifies the AWS region name.
#?   Default is using the region in your AWS CLI profile.
#?
#?   [-x STACKS ...]
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
#?   The manager stack is always being deployed before the node stacks.
#?
#?   The default STACKS is `00`.
#?
#?   [-p PROFILES ...]
#?
#?   The PROFILES specifies the AWS CLI profile that will be used for creating
#?   stacks.
#?   The STACKS option argument is a whitespace separated set of profile names.
#?   The order of the profile names matters.
#?
#?   [-u NAMES ...]
#?
#?   The NAMES specifies the names of the stacks that will be updated.
#?   If this option presents, the update process is taken rather than the
#?   create process.
#?   The NAMES option argument is a whitespace separated set of stack names.
#?   The order of the stack names matters.
#?
#?   -c CONFS [...]
#?
#?   The CONFS specifies the config files that will be operated on.
#?   The CONFS option argument is a whitespace separated set of file names.
#?   The order of the file names matters.
#?
#?   [-h]
#?
#?   This help.
#?
#? Example:
#?   # creating 1 manager stack and 3 node stacks:
#?   $ deploy.sh -x {0..3} -p profile-{0..3} -c vpn-{0..3}-sample.conf
#?
#?   # update existing stacks:
#?   $ deploy.sh -x {0..3} -p profile-{0..3} -c vpn-{0..3}-sample.conf -u vpn-{0..3}-sample
#?

PARAM_MAPPINGS=(
    AccountId:SSMAccountId
    VpcPeerAcceptorRegion:VpcPeerAcceptorRegion
    VpcId:VpcPeerAcceptorVpcId
    VpcPeerAcceptorSqsQueueUrl:VpcPeerAcceptorSqsQueueUrl
    IamPeerRoleArn:VpcPeerAcceptorRoleArn
    SnsTopicArnForConfig:SnsTopicArn
)

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
        # shellcheck disable=SC2046
        seq $(awk -F- '{print $1, $NF}' <<< "${range:?}")
    done | sort -n | uniq
}

function update-config () {
    declare file=${1:?} stack=${2:?} region=$3 json=$4 keypair

    echo "updating config file: $file ..."

    if [[ $stack -gt 0 && -n $json ]]; then
        declare item output_key input_key value
        for item in "${PARAM_MAPPINGS[@]}"; do
            output_key=${item%%:*}
            input_key=${item##*:}
            value="$(get-stack-output-param "$json" "$output_key")"
            echo "updating OPTIONS: $input_key ..."
            # (^\|[^a-zA-Z0-9_]): to match word boundary, for both GNU and BSD sed
            xsh /util/sed-regex-inplace "s|(^\|[^a-zA-Z0-9_])${input_key}=[^\"]*|\1${input_key}=${value}|" "$file"
        done
    fi

    if [[ -z $region ]]; then
        region=$(aws configure get default.region)
    fi
    echo "updating OPTIONS: KeyPairName ..."
    xsh /util/sed-inplace "/KeyPairName=/ s|<REGION>|$region|" "$file"

    keypair=$(get-keypairname "$file")
    if ! xsh aws/ec2/key/exist -r "$region" "$keypair"; then
        echo "creating EC2 key pair: $keypair ..."
        xsh aws/ec2/key/create -r "$region" -f ~/.ssh/"$keypair" "$keypair"
    fi
}

function get-stack-output-param () {
    declare json=${1:?} name=${2:?}
    xsh /json/parser eval "$json" "[item['OutputValue'] for item in {JSON}['Stacks'][0]['Outputs'] if item['OutputKey'] == '""$name""'][0]"
}

function get-keypairname () {
    declare file=${1:?}
    awk -F= '/KeyPairName=/ {print $2}' "$file" | tr -d \'\"
}

function activate () {
    declare profile=$1
    if [[ -n $profile ]]; then
        xsh aws/cfg/activate "$profile"
    fi
}

function create-stack () {
    declare conf=${1:?} region=$2
    echo "creating stack with config: $conf ..."
    xsh aws/cfn/deploy -r "$region" -C "$BASE_DIR" -t stack.json -c "$conf"
}

function update-stack () {
    declare conf=${1:?} name=${2:?} region=$3
    echo "updating stack $name with config: $conf ..."
    echo yes | xsh aws/cfn/deploy -r "$region" -C "$BASE_DIR" -t stack.json -c "$conf" -s "$name" -D
}

function deploy-stack () {
    declare conf=${1:?} name=$2 region=$3
    if [[ -z $name ]]; then
        create-stack "$conf" "$region"
    else
        update-stack "$conf" "$name" "$region"
    fi
}

function main () {
    declare region stacks=00 profiles confs names\
            OPTIND OPTARG opt

    xsh import /util/getopts/extra

    while getopts r:x:p:c:u:h opt; do
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
            c)
                x-util-getopts-extra "$@"
                confs=( "${OPTARG[@]}" )
                ;;
            u)
                x-util-getopts-extra "$@"
                names=( "${OPTARG[@]}" )
                ;;
            *)
                usage
                exit 255
                ;;
        esac
    done
    # shellcheck disable=SC2128
    if [[ -z $stacks || -z $confs ]]; then
        usage
        exit 255
    fi

    # build stack list
    # shellcheck disable=SC2128
    if [[ $stacks == 00 ]]; then
        stacks=( "$stacks" )
    else
        # shellcheck disable=SC2207
        stacks=( $(expansion "${stacks[@]}") )
    fi

    declare stack index tmpfile=/tmp/aws-cfn-vpn-$RANDOM mgr_stack_name json
    # loop the list to deploy manager stack and update all confs
    for stack in "${stacks[@]}"; do
        index=$((stack))
        activate "${profiles[index]}"
        update-config "${confs[index]}" "$stack" "$region" "$json"

        if [[ $stack -eq 0 ]]; then
            deploy-stack "${confs[index]}" "${names[index]}" "$region" | tee "$tmpfile"
            mgr_stack_name=$(awk -F/ '/"StackId":/ {print $2}' "$tmpfile")

            if [[ -n $mgr_stack_name ]]; then
                json=$(xsh aws/cfn/stack/desc -r "$region" -s "$mgr_stack_name")
            else
                echo "failed to get stack name."
                exit 255
            fi
        fi
    done

    # loop the list to deploy all node stacks
    for stack in "${stacks[@]}"; do
        index=$((stack))
        activate "${profiles[index]}"

        if [[ $stack -gt 0 ]]; then
            deploy-stack "${confs[index]}" "${names[index]}" "$region"
        fi
    done
}

declare BASE_DIR
BASE_DIR=$(cd "$(dirname "$0")"; pwd)

main "$@"

exit
