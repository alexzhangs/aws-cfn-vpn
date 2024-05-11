[![GitHub tag](https://img.shields.io/github/v/tag/alexzhangs/aws-cfn-vpn?sort=date)](https://github.com/alexzhangs/aws-cfn-vpn/tags)
[![GitHub](https://img.shields.io/github/license/alexzhangs/aws-cfn-vpn.svg?style=flat-square)](https://github.com/alexzhangs/aws-cfn-vpn/)
[![GitHub last commit](https://img.shields.io/github/last-commit/alexzhangs/aws-cfn-vpn.svg?style=flat-square)](https://github.com/alexzhangs/aws-cfn-vpn/commits/master)

[![GitHub issues](https://img.shields.io/github/issues/alexzhangs/aws-cfn-vpn.svg?style=flat-square)](https://github.com/alexzhangs/aws-cfn-vpn/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/alexzhangs/aws-cfn-vpn.svg?style=flat-square)](https://github.com/alexzhangs/aws-cfn-vpn/pulls)

# aws-cfn-vpn

AWS CloudFormation Stack for VPN services.

This Repo use AWS CloudFormation to automate the deployment of Shadowsocks
and L2TPD, and is trying to make the deployment as easy as possible.

Additionally, it's also deploying
[shadowsocks-manager](https://github.com/alexzhangs/shadowsocks-manager)
which is a web-based Shadowsocks management tool for multi-user and traffic statistics,
support multi-node, creating DNS records, and syncing IPs to name.com.

![stack list](/assets/images/aws-cfn-vpn.png)

## Services List

* Shadowsocks-libev
* L2TPD

## Features

Shadowsocks-libev:

* Users(ports) are managed by
[shadowsocks-manager](https://github.com/alexzhangs/shadowsocks-manager).
* Sending the account Email.
* Multi nodes(across multi AWS accounts).
* Active/Inactive users and nodes.
* Heartbeat to detect the port alive on the node.
* Auto-create the DNS records for the domains of the web console, L2TP,
  and Shadowsocks nodes in [name.com](https://name.com).
* Auto-sync the node info to shadowsocks-manager.
* Auto-sync the node IP address to [name.com](https://name.com).
* Traffic statistics on ports and nodes(minimize the impact of
  node restart).
* Change node IP address from:
    * Web console
    * scheduled job
    * Amazon Lex chatbot
    * REST API
    * AWS SNS message
* Support v2ray-plugin on node level.

L2TPD:

* User management in the command line.

## Overview

This stack leverages several other repos to achieve the work, below
gives an overview of the inside dependency structure. All the internal
dependencies will be installed automatically except `aws-ec2-ses`.

```
aws-cfn-vpn (github)
├── aws-cfn-vpc (github)
├── aws-cfn-vpc-peer-acceptor (github)
├── aws-cfn-vpc-peer-requester (github)
├── aws-cfn-config-provider (github)
├── aws-cfn-vpn-lexbot (github)
├── aws-cfn-acm (github)
├── shadowsocks-libev-v2ray (dockerhub)
│   ├── shadowsocks-libev (dockerhub)
│   ├── v2ray-plugin (github)
|   └── acme.sh (github)
├── shadowsocks-manager (dockerhub)
│   ├── django (pip)
│   └── [aws-ec2-ses (github)] - Manually setup involved
├── aws-ec2-xl2tpd (github)
│   ├── openswan (yum)
│   └── xl2tpd (yum)
└── chap-manager (github)
```

## Insight

### stack.json

This repo contains a standard AWS CloudFormation template `stack.json`
which can be deployed with AWS web console, AWS CLI, or any other AWS
CloudFormation compatible tool.

This template will create an AWS CloudFormation stack, including
following resources:

* 1 EC2 Instance.
    * Shadowsocks-libev is installed if set `EnableSSN=1`.
    * shadowsocks-manager is installed if set `EnableSSM=1`.
    * v2ray-plugin is installed if set `EnableV2ray=1`.
    * L2TPD is installed if set `EnableL2TP=1`.

    For the input parameters and the detail of the template, please check the template
file [stack.json](https://github.com/alexzhangs/aws-cfn-vpn).

* 1 nested VPC stack.

    For the details check [aws-cfn-vpc](https://github.com/alexzhangs/aws-cfn-vpc).

* 1 nested VPC peer acceptor stack if set `EnableVpcPeerAcceptor=1`.

    It accepts the VPC peer connection request from another VPC. The VPC peer connection is used to create a private network connection between the manager stack and node stack, to protect the multi-user API from opening to the public internet.

    For the details check
    [aws-cfn-vpc-peer-acceptor](https://github.com/alexzhangs/aws-cfn-vpc-peer-acceptor).

* 1 nested VPC peer requester stack if set `EnableVpcPeerRequester=1`.

    It sends a request to the acceptor to create a VPC peer connection.

    For the details check
    [aws-cfn-vpc-peer-requester](https://github.com/alexzhangs/aws-cfn-vpc-peer-requester).

* 1 nested Config service stack if set `EnableConfigProvider=1`.

    It setup Config service, to send the config events to the manager
    stack so that the EC2 instances and EIP can be registered automatically.

    The following chart shows how it works.

    | Manager&Node Stacks           | Manager Stack                   |
    |-------------------------------|---------------------------------|
    | Config events → S3 bucket →   | → SNS -> Lambda → SSM REST APIs |

    For the details check
    [aws-cfn-config-provider](https://github.com/alexzhangs/aws-cfn-config-provider).

* 1 Lex chat bot if set `EnableLexBot=1`.

    The chatbot is used to manage the node stacks.

    The following chart shows the deployment topology and the control flow.

    | 3rd Part Apps                 | Manager Stack        | Node Stacks                           |
    |-------------------------------|----------------------|---------------------------------------|
    | Facebook, Slack, ... → text → | → Lex bot → Lambda → | → SNS → Lambda → CloudFormation → EIP |

    For the details check
    [aws-cfn-vpn-lexbot](https://github.com/alexzhangs/aws-cfn-vpn-lexbot).

* 1 nested ACM service stack if set `EnableSSM=1` and `SSMDomain` is
used.

    It set up AWS Certificate Manager service on the manager stack, to automate certificates provision.

    The following chart shows how it works.

    | Manager Stacks           | 3rd DNS Service Provider |
    |--------------------------|--------------------------|
    | Custom Resource → Lambda | → API → DNS Records      |

    For the details check
    [aws-cfn-acm](https://github.com/alexzhangs/aws-cfn-acm).

### sample-*.conf

`sample-*.conf` are config files used by `aws/cfn/vpn/deploy` to automate AWS CloudFormation template deployment.

> `aws/cfn/vpn/deploy` can be installed from repo [xsh-lib/aws](https://github.com/xsh-lib/aws).

## Classic Deployment Scenarios

There are 2 classic deployment scenarios:

1. Deploy a single stack with everything inside, including
shadowsocks-manager, Shadowsocks node, and L2TPD. This method is not
recommended, the shadowsocks-manager will be unreachable once the
node's network goes wrong.
There's 1 sample config file for this.

    * sample-00-sb.conf

1. Deploy at least 2 stacks, one for shadowsocks-manager and L2TPD,
one or more for Shadowsocks nodes. Each one needs to be deployed in a
different AWS account. That allows you to balance network traffic between AWS accounts.
There are 3 sample config files for this.

    * sample-0-sb.conf
    * sample-1-sb.conf
    * sample-2-sb.conf

## Domain Name Design

There are 3 DNS hostnames needed for your services:

1. The domain name pointing to shadowsocks-manager service, such
as `admin.ss.yourdomain.com`.

1. The domain name pointing to L2TPD services, such as
`vpn.yourdomain.com`.

1. The domain name pointing to Shadowsocks nodes, such as
`ss.yourdomain.com`, or `v2ray.ss.yourdomain.com` for v2ray plugin enabled nodes.

## Deploy

The sample deployment is deploying 3 stacks, one for shadowsocks-manager and L2TPD, two for
Shadowsocks nodes.

### Prepare at local

Several tools are needed in the deployment, below shows how to get
them ready.

1. awscli: Install it from [here](https://aws.amazon.com/cli/).

1. [xsh](https://github.com/alexzhangs/xsh): xsh is a bash library framework.

    ```bash
    $ git clone https://github.com/alexzhangs/xsh
    $ bash xsh/install.sh
    ```

1. [xsh-lib/core](https://github.com/xsh-lib/core) and [xsh-lib/aws](https://github.com/xsh-lib/aws)

    ```bash
    $ xsh load xsh-lib/core
    $ xsh load xsh-lib/aws
    ```

Note: If you are proceeding without the tools, then you will have to manually
edit config files and upload templates and Lambda functions to S3, and handle
the parameters for each nested template, which is most people want to avoid.

### Prepare AWS Accounts

1. Sign up [AWS accounts](https://aws.amanzon.com) if you don't have one.

    You will need more than one account if planning to deploy multi-node stacks.

1. Create an IAM user and give it admin permissions in each AWS account.

    This can be done with AWS CLI if you already have the access key
    configured for the account:

    ```sh
    $ aws iam create-user --user-name admin
    $ aws iam attach-user-policy --user-name admin --policy-arn "arn:aws:iam::aws:policy/AdministratorAccess"
    ```

    Otherwise, just use the AWS web console.

    NOTE: You must create an [AWS IAM user](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_users.html)
    or role to deploy the stacks, you can not use
    [AWS root user](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_root-user.html)
    or its access key to do the deployment. Because there is IAM assume role inside the template,
    which assumes an action `ec2:AcceptVpcPeeringConnection` and AWS restricts it's can't be assumed
    by the root user.

1. Create an access key for each IAM user created in the last step.

    This can be done with AWS CLI if you already have the access key
    configured for the account:

    ```sh
    $ aws iam create-access-key --user-name admin
    ```

    Otherwise, just use the AWS web console.

1. Create a profile for each access key created in the last step.

    Following commands will create three profiles with names:
    `vpn-0`, `vpn-1`, and `vpn-2` which will be used in
    the rest of this document.

    A region is needed to be set in this step.

    ```sh
    $ aws configure --profile=vpn-0
    $ aws configure --profile=vpn-1
    $ aws configure --profile=vpn-2
    ```

### Get the code

In the same directory:

```sh
$ git clone https://github.com/alexzhangs/aws-cfn-vpn
$ git clone https://github.com/alexzhangs/aws-cfn-vpc
$ git clone https://github.com/alexzhangs/aws-cfn-vpc-peer-acceptor
$ git clone https://github.com/alexzhangs/aws-cfn-vpc-peer-requester
$ git clone https://github.com/alexzhangs/aws-cfn-config-provider
$ git clone https://github.com/alexzhangs/aws-cfn-vpn-lexbot
$ git clone https://github.com/alexzhangs/aws-cfn-acm
```

### Create the manager stack and the node stacks

#### Simplest Way

The simplest way to create the stacks is to use the high-level wrapper command `aws/cfn/vpn/cluster` provided by the `xsh-lib/aws` library.

```bash
# Set the environment variables
XSH_AWS_CFN_VPN_ENV=sb  # sb stands for sandbox
XSH_AWS_CFN_VPN_DOMAIN=Example.com  # replace with your domain
XSH_AWS_CFN_VPN_DNS=name.com
XSH_AWS_CFN_VPN_DNS_USERNAME=DomainNameServerUsername  # replace with your name.com API username
XSH_AWS_CFN_VPN_DNS_CREDENTIAL=DomainNameServerCredential  # replace with your name.com API credential
#XSH_AWS_CFN_VPN_PLUGINS=v2ray  # uncomment this if want to enable v2ray-plugin

# Create the config files and deploy the stacks at once
xsh aws/cfn/vpn/cluster -x 0-2 -c vpn -C aws-cfn-vpn
```

The options listed above is the best practice for the deployment. It minimizes the manual work and the risk of errors, also provides the best security.

However, it requires you own a domain in [name.com](https://name.com) and have the name.com API enabled.

`DomainNameServerUsername` and `DomainNameServerCredential` are the API credentials of name.com. They are used to create and update the DNS records for the domains of the web console, L2TP, and Shadowsocks nodes. The TLS certificate (for web console) provision process also depends on it to be fully automated.

The API credentials can be generated at your
[name.com API settings](https://www.name.com/account/settings/api).

The command takes around 30 minutes to complete. If everything goes smoothly, you will get 1 manager stack with the L2TPD enabled, and 2 Shadowsocks node stacks with traffic balanced by DNS. You will be able to log in to your manager stack web console with the domain name without any additional setting. 

3 config files are created in the directory `aws-cfn-vpn` along with the deployment:

* vpn-0-sb.conf
* vpn-1-sb.conf
* vpn-2-sb.conf

#### The Way without API Credentials

```bash
# Set the environment variables
XSH_AWS_CFN_VPN_ENV=sb  # sb stands for sandbox
XSH_AWS_CFN_VPN_DOMAIN=Example.com  # replace with your domain

# Create the config files and deploy the stacks at once
xsh aws/cfn/vpn/cluster -x 0-2 -c vpn -C aws-cfn-vpn
```

If the domain is enabled without API credentials, you need to
manually create a DNS record to validate the newly created ACM
certificate. Visit
[AWS ACM service](https://console.aws.amazon.com/acm)
console for the manager stack AWS account, to obtain the DNS record info. Once the ACM certificate is validated successfully, the creation will proceed.

#### The Way without Domain

```bash
# Set the environment variables
XSH_AWS_CFN_VPN_ENV=sb  # sb stands for sandbox

# Create the config files and deploy the stacks at once
xsh aws/cfn/vpn/cluster -x 0-2 -c vpn -C aws-cfn-vpn

# See the help document of the command for the details
xsh help aws/cfn/vpn/cluster
```

If the domain is not enabled at all, the manager stack web console is not HTTPS secured. Therefore, the user and password of web console are sent in plain text. The L2TPD service and the Shadowsocks nodes are not accessible with a domain name, only with the public IP of the EC2 instance.

### Verify the manager stack deployment.

Open your browser, visit `http://<PUBLIC_IP>/admin`, a login screen should show up.

Or visit `https://admin.ss.yourdomain.com/admin`. Note that you
must use the HTTPS protocol with using the domain, the HTTP protocol
won't work with it.

Log in with the default username and password defined within `vpn-0-sb.conf`:

```ini
"SSMAdminUsername=admin"
"SSMAdminPassword=passw0rd"
```

## Maintain DNS Records

If the DNS service API is enabled, then you can skip the following steps,
shadowsocks-manager should have taken care of the DNS records.

If you are not in the case above, proceed with the following steps:

1. Create a DNS `CNAME record`, such as `admin.ss`.yourdomain.com,
pointing to the public DNS name of the ELB of the manager stack.

    Use this domain to access the shadowsocks-manager.

1. Create a DNS `A record`, such as `vpn`.yourdomain.com, pointing to the
public IP of EC2 Instance of manager stack.

    Use this domain to access the L2TP service.

1. Create a DNS `A record`, such as `ss`.yourdomain.com pointing to
the public IP of EC2 Instance of node stack.

    Use this domain to access the Shadowsocks service.

## Configure shadowsocks-manager

1. Log in to the shadowsocks-manager web console at
`https://admin.ss.yourdomain.com/admin` after the DNS records get
effective.

1. Go to `Home › Shadowsocks › Shadowsocks Nodes`, to check the node
list, all node stacks you created should have been registered as nodes
automatically.

    Note: The registration relies on the AWS Config, SNS, and Lambda services,
it takes up to around 5 minutes to capture and deliver the config changes.

1. Now you are ready to create Shadowsocks accounts on the web
   console, or import the previously exported accounts back.

## Verify L2TPD services

Use your L2TPD client to connect to the service.

With macOS High Sierra, you can choose the built-in L2TPD client:

```ini
Interface: VPN
VPN Type: L2TP over IPSec
```

The default credential defined within `vpn-0-sb.conf` is:

```ini
"L2TPUsername=vpnuser"
"L2TPPassword=passw0rd"
"L2TPSharedKey=SharedSecret"
```

## v2ray-plugin

[V2ray-plugin](https://github.com/shadowsocks/v2ray-plugin) is optionally supported for the Shadowsocks nodes in Websocket (HTTPS) mode.

This feature is experimental and is disabled by default. It requires several options to be set properly in the node stack config file.

```ini
"EnableV2ray=1"
"SSDomain=<v2ray.ss.yourdomain.com>"
"DomainNameServer=name.com"
"DomainNameServerUsername=<YourDomainNameServerUsername>"
"DomainNameServerCredential=<YourDomainNameServerCredential>"
```

Use below command to deploy v2ray-plugin enabled nodes:

```bash
XSH_AWS_CFN_VPN_PLUGINS=v2ray xsh aws/cfn/vpn/cluster -x {0..2} -c vpn -C aws-cfn-vpn
```

[acme.sh](https://github.com/acmesh-official/acme.sh) is internally used to provision additional TLS certificate for v2ray-plugin automatically. This certificate is used for the domain `v2ray.ss.yourdomain.com`. 

The corresponding client settings are:

```ini
plugin: v2ray-plugin
plugin_opts: tls;host=v2ray.ss.yourdomain.com
```

> NOTE: The v2ray-plugin is set on node level, all accounts creating on this node are going to be v2ray enabled.

## Customize the Deployment

The deployment can be customized by editing the config files, or their templates at `aws-cfn-vpn/config-templates` before to generate config files.

Also the deployment can be customized by using the low-level wrapper command `aws/cfn/vpn/config` and `aws/cfn/vpn/deploy` provided by the `xsh-lib/aws` library.

See help document of the commands for the details.

```bash
xsh list aws/cfn/vpn
xsh help aws/cfn/vpn/config
xsh help aws/cfn/vpn/deploy
```

## Tips

1. How to change the IP address of the EC2 instance of the Manager stack
   or the Node stack?

    Update the stack with a new value of parameter `EipDomain`, switch the
the value between `vpc` and an empty string ``, this will change the EIP
of the EC2 instance.

    DO NOT operate on the EIP directly, such as allocate a new EIP
and associate it, then release the old. This will cause an error
in locating the original EIP resource when operating on the stack
level.

    For the EC2 instance of the Node stacks, the following methods are recommended:

    * Use the admin web console at `Home › Shadowsocks › Shadowsocks Nodes`.
    * Use the Lex chatbot.

1. How to enable the HTTPS(SSL certificate) for the Manager stack?

    HTTPS will be enabled by default if you specify a domain for the
    template parameter `SSMDomain`.

    The TLS certificate is issued for the domain `SSMDomain` with AWS
    ACM service, the service is free, there's no charge for the certificates.

## Development

### Re-generate the sample config files

```bash
# Unset the environment variables if they are set, otherwise the command will use the values in the environment.
unset XSH_AWS_CFN_VPN_ENV \
    XSH_AWS_CFN_VPN_DOMAIN \
    XSH_AWS_CFN_VPN_DNS \
    XSH_AWS_CFN_VPN_DNS_USERNAME \
    XSH_AWS_CFN_VPN_DNS_CREDENTIAL \
    XSH_AWS_CFN_VPN_PLUGINS

# Generate the sample config file(s): sample-00-sb.conf
xsh aws/cfn/vpn/config -x 00 -p vpn-0 -b sample -e sb

# Generate the sample config file(s): sample-0-sb.conf, sample-1-sb.conf, sample-2-sb.conf
xsh aws/cfn/vpn/config -x 0-2 -p vpn-{0..2} -b sample -e sb
```

### Create the Lambda Layer Packages

1. requests

    ```bash
    cd lambdas/layers
    mkdir -p python
    pip install requests -t python
    zip -r9 LambdaLayerRequests.zip python
    rm -rf python
    ```
1. tldextract

    ```bash
    cd lambdas/layers
    mkdir -p python
    pip install tldextract -t python
    zip -r9 LambdaLayerTldExtract.zip python
    rm -rf python
    ```

* https://www.keyq.cloud/en/blog/creating-an-aws-lambda-layer-for-python-requests-module
* https://aws.amazon.com/blogs/compute/upcoming-changes-to-the-python-sdk-in-aws-lambda/


## TODO

* Add a default Shadowsocks user like the default user for L2TPD.

## Troubleshooting

1. The stack ends up at 'CREATE_FAILED' status.

    Log in to the AWS web console, go to CloudFormation, check the event
    list of the stack, found the failed events to locate the root reason,
    check the event list of the nested stack if necessary.

1. For any problem related to the repos that aws-cfn-vpn depends
on, check with the depended repos, here is the quick dial of star
gates.

   1. [aws-cfn-vpc](https://github.com/alexzhangs/aws-cfn-vpc)
   1. [aws-cfn-vpc-peer-acceptor](https://github.com/alexzhangs/aws-cfn-vpc-peer-acceptor)
   1. [aws-cfn-vpc-peer-requester](https://github.com/alexzhangs/aws-cfn-vpc-peer-requester)
   1. [aws-cfn-config-provider](https://github.com/alexzhangs/aws-cfn-config-provider)
   1. [aws-cfn-vpn-lexbot](https://github.com/alexzhangs/aws-cfn-vpn-lexbot)
   1. [aws-cfn-acm](https://github.com/alexzhangs/aws-cfn-acm)
   1. ~~[aws-ec2-shadowsocks-libev](https://github.com/alexzhangs/aws-ec2-shadowsocks-libev)~~
   1. [shadowsocks-libev-v2ray](https://github.com/alexzhangs/shadowsocks-libev-v2ray)
   1. [shadowsocks-manager](https://github.com/alexzhangs/shadowsocks-manager)
   1. [aws-ec2-ses](https://github.com/alexzhangs/aws-ec2-ses)
   1. [aws-ec2-xl2tpd](https://github.com/alexzhangs/aws-ec2-xl2tpd)
   1. [chap-manager](https://github.com/alexzhangs/chap-manager)

1. Failed to delete the manager stack.

   If VPC peer connections exist in the manager stacks, deleting the stacks will fail.

   Solution:

   1. Delete all the node stacks before deleting the manager stack.

   2. Manually delete all existing peer connections belong to that stack first. This can be done with AWS web console, or the CLI:

        ```sh
        $ aws ec2 describe-vpc-peering-connections
        $ aws ec2 delete-vpc-peering-connection --vpc-peering-connection-id <peering-connection-id>
        ```

1. Encountering errors while executing EC2 userdata.

   This might be caused by using the untested AWS AMI.
   The EC2 userdata is tested only with the following AMIs:

   * Amazon Linux AMI 2018.03.0 (HVM), SSD Volume Type
   * Amazon Linux 2 AMI (HVM), SSD Volume Type - This AMI is
     **RECOMMENDED** for `aws-cfn-vpn`

   Feel free to open pull requests for the verified compatible AMIs.
