#!/bin/bash

set -e -o pipefail

#? Description:
#?   Deploy AWS CloudFormation stacks from the template and the config files.
#?
#? Usage:
#?   deploy.sh [-r REGION] [-x STACKS ...] [-p PROFILES ...] [-u NAMES ...] -c CONFS ...
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
#?   The default STACKS is '0-1', which selects the only manager stack and 1 node
#?   stack.
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
#?   -c CONFS ...
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
#?   # create new stacks
#?   deploy.sh -x {0..3} -p profile-{0..3} -c vpn-{0..3}-sample.conf
#?
#?   # update existing stacks
#?   deploy.sh -x {0..3} -p profile-{0..3} -c vpn-{0..3}-sample.conf -u vpn-{0..3}-sample
#?

PARAM_MAPPINGS=(
    AccountId:SSMAccountId
    VpcPeerAccepterRegion:VpcPeerAccepterRegion
    VpcId:VpcPeerAccepterVpcId
    VpcPeerAccepterSqsQueueUrl:VpcPeerAccepterSqsQueueUrl
    IamPeerRoleArn:VpcPeerAccepterRoleArn
    SnsTopicArnForConfig:SnsTopicArn
)

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
            xsh /util/sed-inplace "s|[[:<:]]${input_key}=[^\"]*|${input_key}=${value}|" "$file"
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
    xsh /json/parser eval "$json" "[item['OutputValue'] for item in {JSON}['Stacks'][0]['Outputs'] if item['OutputKey'] == '"$name"'][0]"
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
    declare region stacks=0-1 profiles confs names\
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
    if [[ $# -eq 0 ]]; then
        usage
        exit 255
    fi

    # build stack list
    if [[ -n $stacks ]]; then
        stacks=(
            $(for item in $stacks; do
                  seq -s '\n' $(expension "$item");
              done | sort -n | uniq)
        )
    else
        usage
        exit 255
    fi

    # loop the list to deploy stacks
    declare stack tmpfile=/tmp/aws-cfn-vpn-$RANDOM mgr_stack_name json
    for stack in ${stacks[@]}; do
        activate "${profiles[stack]}"
        update-config "${confs[stack]}" "$stack" "$region" "$json"

        if [[ $stack -eq 0 ]]; then
            deploy-stack "${confs[stack]}" "${names[stack]}" "$region" | tee "$tmpfile"
            mgr_stack_name=$(awk -F/ '/"StackId":/ {print $2}' "$tmpfile")

            if [[ -n $mgr_stack_name ]]; then
                json=$(xsh aws/cfn/stack/desc -r "$region" -s "$mgr_stack_name")
            else
                echo "failed to get stack name."
                exit 255
            fi
        else
            deploy-stack "${confs[stack]}" "${names[stack]}" "$region"
        fi
    done
}

declare BASE_DIR=$(cd "$(dirname "$0")"; pwd)

main "$@"

exit