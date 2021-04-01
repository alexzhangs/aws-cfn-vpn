#!/bin/bash

set -e -o pipefail

#? Description:
#?   Create the config file(s) from templates, and update them by the command
#?   line options.
#?
#? Usage:
#?   config.sh
#?     [-x STACKS]
#?     [-n NAME]
#?     [-e ENVIRONMENT]
#?     [-S]
#?     [-d DOMAIN]
#?     [-N DNS]
#?     [-u DNS_USERNAME]
#?     [-p DNS_CREDENTIAL]
#?     [-h]
#?
#? Options:
#?   [-x STACKS]
#?
#?   The STACKS specifies the stacks index that will be operated on.
#?   The STACKS option argument is a whitespace separated set of numbers and/or
#?   number ranges. Number ranges consist of a number, a dash ('-'), and a second
#?   number and select the stacks from the first number to the second, inclusive.
#?
#?   Numbers or number ranges may be preceded by a dash, which selects all stacks
#?   from 0 to the last number.
#?
#?   The number 0 is specially held for the manager stack, and the rest numbers
#?   started from 1 is for the node stacks.
#?
#?   The number 00 is specially held for a single stack that puts the manager
#?   and the node together.
#?
#?   The default STACKS is 00.
#?
#?   [-n NAME]
#?
#?   The NAME specifies the base stack name.
#?   Default is 'vpn'.
#?
#?   [-e ENVIRONMENT]
#?
#?   The ENVIRONMENT specifies the environment name.
#?   Default is 'sample'.
#?
#?   [-S]
#?
#?   Do not add a random suffix to the stack name.
#?   Default is adding a random suffix to the stack name.
#?
#?   [-d DOMAIN]
#?
#?   The DOMAIN specifies the base domain name.
#?
#?   [-N DNS]
#?
#?   The DNS specifies the Domain Nameserver for the DOMAIN.
#?   Supported Nameserver: 'name.com'.
#?
#?   [-u DNS_USERNAME]
#?
#?   The DNS_USERNAME specifies the user identity for the Domain Nameserver API service.
#?
#?   [-p DNS_CREDENTIAL]
#?
#?   The DNS_CREDENTIAL specifies the user credential/token for the Domain Nameserver API service.
#?
#?   [-h]
#?
#?   This help.
#?
#? Example:
#?   # creating 1 manager config file and 3 node config files:
#?   $ config.sh -x 0-3
#?
#?   # creating 1 manager config file and 3 node config files using domain
#?   #  plus the Nameserver API enabled:
#?   $ config.sh -x 0-3 -d example.com -n name.com -u myuser -p mytoken
#?

function usage () {
    awk '/^#\?/ {sub("^[ ]*#\\?[ ]?", ""); print}' "$0" \
        | awk '{gsub(/^[^ ]+.*/, "\033[1m&\033[0m"); print}'
}

function create-config () {
    declare file=${1:?} stack=${2:?}

    echo "generating config file: $file ..."
    xsh aws/cfn/deploy -g > "$file"

    declare param n=$stack
    if [[ $n -gt 1 ]]; then
        n=1
    fi

    # update DEPENDS LAMBDA LOGICAL_ID OPTIONS
    for param in DEPENDS LAMBDA LOGICAL_ID OPTIONS; do
        echo "updating $param ..."
        xsh /util/sed-inplace "/^$param=[^\"]*/ {
                                  r /dev/stdin
                                  d
                              }" "$file" \
            <<< "$(cat "$BASE_DIR/config-templates/$param-COMMON.conf" \
                       "$BASE_DIR/config-templates/$param-$n.conf")"
    done

    # update for OPTIONS: VpcCidrBlock SubnetCidrBlocks
    echo "updating OPTIONS: CIDR blocks ..."
    xsh /util/sed-inplace "/CidrBlock/ s|<N>|$((stack))|g" "$file"
}

function update-config () {
    declare file=${1:?} stack=${2:?} stack_name=${3:?} environment=${4:?} \
            random_stack_name_suffix=${5:?} domain=$6 DomainNameServer=$7 \
            DomainNameServerUsername=$8 DomainNameServerCredential=$9

    echo "updating config file: $file ..."

    # update STACK_NAME ENVIRONMENT RANDOM_STACK_NAME_SUFFIX
    declare param lower_param
    for param in STACK_NAME ENVIRONMENT RANDOM_STACK_NAME_SUFFIX; do
        lower_param=$(xsh /string/lower "$param")
        echo "updating $param ..."
        xsh /util/sed-inplace "s|^$param=[^\"]*|$param=${!lower_param}|" "$file"
    done

    declare KeyPairName="aws-ek-$stack_name-$environment-<REGION>" \
            Domain SSMDomain SSMAdminEmail L2TPDomain SSDomain

    if [[ -n $domain ]]; then
        # get the root domain
        Domain=$(echo $domain | awk -F. 'NF>1 {OFS=FS; print $(NF-1), $NF}')

        SSMDomain=admin.ss.$domain
        SSMAdminEmail=admin@$domain
        L2TPDomain=vpn.$domain
        SSDomain=ss.$domain
    fi

    # update for OPTIONS:
    #   KeyPairName
    #   Domain SSMDomain SSMAdminEmail L2TPDomain SSDomain
    #   DomainNameServer DomainNameServerUsername DomainNameServerCredential
    for param in KeyPairName Domain SSMDomain SSMAdminEmail L2TPDomain SSDomain \
                 DomainNameServer DomainNameServerUsername DomainNameServerCredential; do
        echo "updating OPTIONS: $param ..."
        # [[:<:]]: to match word boundary
        xsh /util/sed-inplace "s|[[:<:]]$param=[^\"]*|$param=${!param}|" "$file"
    done
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

function main () {
    declare region stacks=00 name=vpn env=sample suffix=1 \
            domain dns dns_username dns_credential \
            OPTAND OPTARG opt

    while getopts r:x:n:e:Sd:N:u:p:h opt; do
        case $opt in
            r)
                region=$OPTARG
                ;;
            x)
                stacks=$OPTARG
                ;;
            n)
                name=$OPTARG
                ;;
            e)
                env=$OPTARG
                ;;
            S)
                suffix=0
                ;;
            d)
                domain=$OPTARG
                ;;
            N)
                dns=$OPTARG
                ;;
            u)
                dns_username=$OPTARG
                ;;
            p)
                dns_credential=$OPTARG
                ;;
            *)
                usage
                exit 255
                ;;
        esac
    done

    # build stack list
    if [[ -z $stacks ]]; then
        usage
        exit 255
    elif [[ $stacks == 00 ]]; then
        stacks=( $stacks )
    else
        stacks=(
            $(for item in $stacks; do
                  seq -s '\n' $(expension "$item");
              done | sort -n | uniq)
        )
    fi

    # loop the list to generate config files
    declare stack stack_name file
    for stack in "${stacks[@]}"; do
        stack_name=$name-$stack
        file=$BASE_DIR/$stack_name-$env.conf

        create-config "$file" "$stack"
        update-config "$file" "$stack" "$stack_name" "$env" \
                         "$suffix" "$domain" "$dns" \
                         "$dns_username" "$dns_credential"
    done
}

declare BASE_DIR=$(cd "$(dirname "$0")"; pwd)

main "$@"

exit
