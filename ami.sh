#!/bin/bash

set -e -o pipefail

#? Description:
#?   Get the latest AMIs for all enabled regions and build JSON in the format
#?   of Region-to-AMI mapping as the key `Mappings` in aws-cfn-vpn template.
#?   It takes a few minutes to finish, please be patient.
#?
#?   All the AMIs are AWS free tier eligible and have the types:
#?     * ImageOwnerAlias: amazon
#?     * Public: true
#?     * State: available
#?     * Architecture: x86_64
#?     * Hypervisor: xen
#?     * VirtualizationType: hvm
#?     * Description: Amazon Linux 2 AMI*
#?
#?   Some regions are not enabled for your account by default. Those regions
#?   will be updated with en empty AMI object: {}.
#?
#?   You can enable the disabled regions in your web console at:
#?   https://console.aws.amazon.com/billing/home?#/account
#?
#? Usage:
#?   ami.sh
#?     [-t TEMPLATE]
#?     [-h]
#?
#? Options:
#?   [-t TEMPLATE]
#?
#?   Update the TEMPLATE file with the new mapping on the key `Mappings`.
#?   The file must be in JSON format and be at local.
#?
#?   [-h]
#?
#?   This help.
#?
#? Example:
#?   # get the latest AMIs to stdout
#?   ami.sh
#?
#?   # update the latest AMIs to stack.json
#?   ami.sh -t stack.json
#?

function usage () {
    awk '/^#\?/ {sub("^[ ]*#\\?[ ]?", ""); print}' "$0" \
        | awk '{gsub(/^[^ ]+.*/, "\033[1m&\033[0m"); print}'
}

function region-long-name () {
    #? Usage:
    #?   region-long-name <REGION>
    #?
    declare region=${1:?}
    aws ssm get-parameters \
        --name /aws/service/global-infrastructure/regions/"$region"/longName \
        --query 'Parameters[0].[Value]' \
        --output text
}

function AMI-ID () {
    #? Usage:
    #?   AMI-ID <REGION>
    #?
    declare region=${1:?}
    aws ssm get-parameters \
        --region "$region" \
        --query 'Parameters[*].[Value]' \
        --names /aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2 \
        --output text
}

function AMI () {
    #? Usage:
    #?   AMI <REGION>
    #?
    declare region=${1:?} filters location id
    # shellcheck disable=SC2191
    # shellcheck disable=SC2054
    filters=(
        Name=owner-alias,Values=amazon
        Name=is-public,Values=true
        Name=state,Values=available
        Name=architecture,Values=x86_64
        Name=description,Values=Amazon\ Linux\ 2\ AMI\*
        Name=hypervisor,Values=xen
        Name=virtualization-type,Values=hvm
    )
    location=$(region-long-name "$region")
    id=$(AMI-ID "$region")
    if [[ -z $id ]]; then
        return
    fi
    aws ec2 describe-images \
        --region "$region" \
        --image-ids "$id" \
        --query 'Images[0].{name:Name,AMI:ImageId,created:CreationDate,location:'"'$location'"'}' \
        --filter "${filters[@]}" \
        --output json
}

function regions () {
    #? Usage:
    #?   regions
    #?
    aws ec2 describe-regions \
        --query 'Regions[*].[RegionName]' \
        --output text
}

function AMIs () {
    #? Usage:
    #?   AMIs
    #?
    declare regions index ami
    # shellcheck disable=SC2207
    regions=( $(regions) )
    for index in "${!regions[@]}"; do
        printf "." >&2
        ami=$(AMI "${regions[index]}" | sed 's/  / /g')  # indent length: 4 => 2
        printf '"%s": %s' "${regions[index]}" "${ami:-{\}}"  # ami: None ==> {}
        if [[ $index -lt $((${#regions[@]} - 1)) ]]; then
            printf ",\n"
        else
            printf "\n"
        fi
    done
    printf "\n" >&2
}

function wrap () {
    #? Usage:
    #?   wrap <AMIs>
    #?
    declare amis=${1:?} indent_amis wrapper
    IFS='' read -r -d '' wrapper <<EOF
"Mappings": {
  "RegionMap": {
%s
  }
}
EOF
    indent_amis=$(printf '%s' "$amis" | sed 's/^/    /')   # indent level: +2
    # shellcheck disable=SC2059
    printf "$wrapper\n" "$indent_amis"
}

function update () {
    #? Usage:
    #?   update <MAPPING> <FILE>
    #?
    declare mapping=${1:?} file=${2:?}
    printf 'updating mapping in: %s ...' "$file"
    xsh /file/inject \
        -c "$mapping" \
        -p before \
        -e '^  "Outputs": \{$' \
        -x '^  "Mappings": \{$' \
        -y '^  \},$' \
        "$file"
    printf " [done]\n"
}

function main () {
    # shellcheck disable=SC2034
    declare template mapping \
            OPTAND OPTARG opt

    while getopts t:h opt; do
        case $opt in
            t)
                template=$OPTARG
                ;;
            *)
                usage
                exit 255
                ;;
        esac
    done

    mapping=$(wrap "$(AMIs)")
    printf '%s\n' "$mapping"

    if [[ -n $template ]]; then
        mapping=${mapping/#/  }  # indent level: +1
        mapping=${mapping},  # append comma
        update "$mapping" "$template"
    fi
}

declare BASE_DIR
# shellcheck disable=SC2034
BASE_DIR=$(cd "$(dirname "$0")"; pwd)

main "$@"

exit
