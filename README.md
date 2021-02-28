# aws-cfn-vpn

AWS CloudFormation Stack for VPN services.

This Repo use AWS CloudFormation to automate the deployment of Shadowsocks
and XL2TPD, and is trying to make the deployment as easier as possible.

Additionally, it's also deploying
[shadowsocks-manager](https://github.com/alexzhangs/shadowsocks-manager)
which is a web-based Shadowsocks management tool for multi-user and traffic statistics,
support multi-node, creating DNS records and syncing IPs to name.com.

## Services List

* Shadowsocks-libev
* XL2TPD

## Features

Shadowsocks-libev:

* Users(ports) are managed by
[shadowsocks-manager](https://github.com/alexzhangs/shadowsocks-manager).
* Sending the account Email.
* Multi nodes(across multi AWS accounts).
* Active/Inactive users and nodes.
* Heartbeat to detect the port alive on the node.
* Auto-create the DNS records for the domains of web console, L2TP,
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

L2TPD:

* User management in the command line.

## Overview

This stack leverages several other repos to achieve the work, below
gives an overview of the inside dependency structure. All the internal
dependencies will be installed automatically except `aws-ec2-ses`.

```
aws-cfn-vpn (github)
├── aws-cfn-vpc (github)
├── aws-cfn-vpc-peer-accepter (github)
├── aws-cfn-vpc-peer-requester (github)
├── aws-cfn-config-provider (github)
├── aws-cfn-vpn-lexbot (github)
├── aws-cfn-acm (github)
├── aws-ec2-shadowsocks-libev (github)
│   └── shadowsocks-libev (yum)
├── shadowsocks-manager (github)
│   ├── django (pip)
│   └── [aws-ec2-ses (github)] - Manually setup involved
├── aws-ec2-xl2tpd (github)
│   ├── openswan (yum)
│   └── xl2tpd (yum)
├── chap-manager (github)
└── aws-ec2-supervisor (github)
     ├── supervisor (pip)
     └── supervisord (github) - The initd script
```

## Insight

### stack.json

This repo contains a standard AWS CloudFormation template `stack.json`
which can be deployed with AWS web console, AWS CLI or any other AWS
CloudFormation compatible tool.

This template will create an AWS CloudFormation stack, including
following resources:

* 1 EC2 Instance.
    * Shadowsocks-libev is installed if set `EnableSSN=1`.
    * shadowsocks-manager is installed if set `EnableSSM=1`.
    * L2TPD is installed if set `EnableL2TP=1`.

    For the input parameters and the detail of the template, please check the template
file [stack.json](https://github.com/alexzhangs/aws-cfn-vpn).

* 1 nested VPC stack.

    For the details check [aws-cfn-vpc](https://github.com/alexzhangs/aws-cfn-vpc).

* 1 nested VPC peer accepter stack if set `EnableVpcPeerAccepter=1`.

    It accepts the VPC peer connection request from another VPC. The VPC peer connection is used to create a private network connection between manager stack and node stack, to protect the multi-user API from opening to the public internet.

    For the details check
    [aws-cfn-vpc-peer-accepter](https://github.com/alexzhangs/aws-cfn-vpc-peer-accepter).

* 1 nested VPC peer requester stack if set `EnableVpcPeerRequester=1`.

    It sends a request to the accepter to create a VPC peer connection.

    For the details check
    [aws-cfn-vpc-peer-requester](https://github.com/alexzhangs/aws-cfn-vpc-peer-requester).

* 1 nested Config service stack if set `EnableConfigProvider=1`.

    It setup Config service on the node stack, to send node change
    events to the manager stack so that the node can be registered
    automatically.

    Following chart shows how it works.

    | Node Stacks | Manager Stack |
    |---|---|
    | Config events → S3 bucket → | → SNS -> Lambda → SSM REST APIs |

    For the details check
    [aws-cfn-config-provider](https://github.com/alexzhangs/aws-cfn-config-provider).

* 1 Lex chat bot if set `EnableLexBot=1`.

    The chatbot is used to manage the node stacks.

    Following chart shows the deployment topology and the control flow.

    | 3rd Part Apps | Manager Stack | Node Stacks |
    |---|---|---|
    | Facebook, Slack, ... → text → | → Lex bot → Lambda → | → SNS → Lambda → CloudFormation → EIP |

    For the details check
    [aws-cfn-vpn-lexbot](https://github.com/alexzhangs/aws-cfn-vpn-lexbot).

* 1 nested ACM service stack if set `EnableSSM=1` and `SSMDomain` is
used.

    It setup AWS Certificate Manager service on the manager stack, to automate certificates provision.

    Following chart shows how it works.

    | Manager Stacks | 3rd DNS Service Provider |
    |---|---|
    | Custom Resource → Lambda | → API → DNS Records |

    For the details check
    [aws-cfn-acm](https://github.com/alexzhangs/aws-cfn-acm).

### sample-*.conf

`sample-*.conf` are config files used by `aws-cfn-deploy` to automate AWS CloudFormation template deployment.

`aws-cfn-deploy` can be installed from repo [xsh-lib/aws](https://github.com/xsh-lib/aws).

## Classic Usage

There are 2 classic deployment methods:

1. Deploy a single stack with everything inside, including
shadowsocks-manager, Shadosocks node, and XL2TPD. This method is not
recommanded, the shadowsocks-manager will be unreachable once the
node's network goes wrong.
There's a sample config file `sample-ssm-and-ssn-0.conf` for this.

1. Deploy at least 2 stacks, one for shadowsocks-manager and XL2TPD,
one or more for Shadowsocks nodes. Each one needs to be deployed in a
different AWS account. That allows you to balance network traffic between AWS accounts.
There are 3 sample config files for this.

    * sample-ssm.conf
    * sample-ssn-1.conf
    * sample-ssn-2.conf

## Domain Name Design

There are 3 DNS hostnames needed for your services:

1. The domain name pointing to shadowsocks-manager service, such
as `admin.ss.yourdomain.com`.

1. The domain name pointing to XL2TPD services, such as
`vpn.yourdomain.com`.

1. The domain name pointing to Shadowsocks nodes, such as
`ss.yourdomain.com`.

If you are deploying a single stack with everything inside, then one domain hostname will work out.

## Deploy

### Prepare at local

Several tools were needed in this deployment, below shows how to get
them ready.

1. awscli: Install it from [here](https://aws.amazon.com/cli/).

1. [xsh](https://github.com/alexzhangs/xsh): xsh is a bash library framework.

```sh
git clone https://github.com/alexzhangs/xsh
bash xsh/install.sh
```

1. [xsh-lib/aws](https://github.com/xsh-lib/aws): xsh-lib/aws is a
library or xsh.

```bash
xsh load xsh-lib/aws
```

Note: If you are proceeding without the tools, then you will have to manually
edit config files and upload templates and Lambda function to S3, and handle
the parameters for each nested templates.

### Prepare AWS Accounts

1. Sign up [AWS accounts](https://aws.amanzon.com) if you don't have.

    You will need more than one account if planning to deploy multi-node stacks.

1. Create an IAM user and give it admin permissions in each AWS account.

    This can be done with AWS CLI if you already have the access key
    configured for the account:

    ```sh
    $ aws iam create-user --user-name admin
    $ aws iam attach-user-policy --user-name admin --policy-arn "arn:aws:iam::aws:policy/AdministratorAccess"
    ```

    Otherwise, just use the AWS web console.

    NOTE: You must create an IAM user or role to deploy the
    stacks, you can not use AWS `root user` or its access key to do the
    deployment. Because there is IAM assume role inside the template,
    which assumes an action `ec2:AcceptVpcPeeringConnection` and AWS
    restricts it's can't be assumed by the root user.

1. Create an access key for each IAM user created in the last step.

    This can be done with AWS CLI if you already have the access key
    configured for the account:

    ```sh
    $ aws iam create-access-key --user-name admin
    ```

    Otherwise, just use the AWS web console.

1. Create a profile for each access key created in the last step.

    Following commands will create three profiles with names:
    `profile-0`, `profile-1`, and `profile-2` which will be used in
    the rest of this document.

    A region is needed to be set in this step.

   ```sh
   $ aws configure --profile=profile-0
   $ aws configure --profile=profile-1
   $ aws configure --profile=profile-2
   ```

### Get the code

In the same directory:

```sh
$ git clone https://github.com/alexzhangs/aws-cfn-vpn
$ git clone https://github.com/alexzhangs/aws-cfn-vpc
$ git clone https://github.com/alexzhangs/aws-cfn-vpc-peer-accepter
$ git clone https://github.com/alexzhangs/aws-cfn-vpc-peer-requester
$ git clone https://github.com/alexzhangs/aws-cfn-config-provider
$ git clone https://github.com/alexzhangs/aws-cfn-vpn-lexbot
$ git clone https://github.com/alexzhangs/aws-cfn-acm
```

### Create the aws-cfn-vpn config files

The config files are needed by `aws-cfn-vpn` to deploy the
CloudFormation stacks. Review the options listed below and choose one from
them:

1. Basic: Create three config files, one is for the
    manager stack, the other two are for the node stacks.

    ```bash
    $ bash aws-cfn-vpn/config.sh -x 0-2
    ```

1. Classic: Use domain and enable HTTPS.
    Add the domain `example.com` to your vpn services, such as the
    admin web console, the l2tp service, and the Shadowsocks service.
    HTTPS will be enabled for the admin web console.

    ```bash
    $ bash aws-cfn-vpn/config.sh -x 0-2 -d EXAMPLE.COM
    ```

1. Advanced: Enable DNS service API with additional settings(only `name.com` for now):

    ```bash
    $ bash aws-cfn-vpn/config.sh -x 0-2 -d EXAMPLE.COM -N name.com -u DomainNameServerUsername -p DomainNameServerCredential
    ```

    With DNS service API enabled, DNS records can be automatically
    maintained, and therefore the ACM certificates provisioning can be
    fully automated.

    `DomainNameServerUsername` and `DomainNameServerCredential` are
    generated at your
    [name.com API settings](https://www.name.com/account/settings/api).

1. Or see the help and figure it out yourself:

    ```bash
    $ bash aws-cfn-vpn/config.sh -h
    ```

After the command is completed, following config files should be
created:

```sh
$ ls -1 aws-cfn-vpn/vpn-*.conf
aws-cfn-vpn/vpn-0-sample.conf
aws-cfn-vpn/vpn-1-sample.conf
aws-cfn-vpn/vpn-2-sample.conf
```

### Create the manager stack and the node stacks

Following command will create three CloudFormation stacks by using
the three AWS CLI profiles and the three config files created in the
earlier steps.

```bash
$ bash aws-cfn-vpn/create.sh -x 0-2 -p "profile-0 profile-1 profile-2" aws-cfn-vpn/vpn-{0..2}-sample.conf
```

If HTTPS is enabled but the DNS service API is not, you need to
manually create DNS record to validate the new created ACM
certificate. Visit
[AWS ACM service](https://console.aws.amazon.com/acm)
console to obtain the DNS record info. Once the ACM certificate is
validated successfully, you can proceed.

The command takes around 30 minutes to complete, and if everything
goes smooth, the 3 stacks and all services should be ready after
the command is completed. You can move to the next section.

### Verify the manager stack deployment.

Open your browser, visit `http://<PUBLIC_IP>/admin`, a login screen should show up.

Or visit `https://admin.ss.yourdomain.com/admin`. Note that you
must use the HTTPS protocol with using the domain, the HTTP protocol
won't work with it.

Log in with the default username and password:

```ini
"SSMAdminUsername=admin"
"SSMAdminPassword=passw0rd"
```

## Maintain DNS Records

If the DNS service API is enabled , then you can skip following steps,
shadowsocks-manager should have taken care of the DNS records.

If you are not in the case above, proceed with following steps:

1. Create a DNS `A record`, such as `admin.ss`.yourdomain.com,
pointing to the public IP of EC2 Instance of manager stack.

    Use this domain to access the shadowsocks-manager.

1. Create a DNS `A record`, such as `vpn`.yourdomain.com, pointing to the
public IP of EC2 Instance of manager stack.

    Use this domain to access to the L2TP service.

1. Create a DNS `A record`, such as `ss`.yourdomain.com pointing to
the public IP of EC2 Instance of node stack.

    Use this domain to access the Shadowsocks service.

## Configure shadowsocks-manager

1. Log in the shadowsocks-manager web console back at
`https://admin.ss.yourdomain.com/admin` after the DNS records get
effective.

1. Go to `Home › Shadowsocks › Shadowsocks Nodes`, to check the node
list, all node stacks you created should have been registered as nodes
automatically.

    Note: The registration relies on the AWS Config, SNS and Lambda services,
it takes up to around 15 minutes to capture and deliver the config changes.

1. Now you are ready to create Shadowsocks accounts in the web
   console, or import the previously exported accounts back.

## Verify XL2TPD services

Use your XL2TPD client to connect to the service.

With macOS High Sierra, you can choose the built-in XL2TPD client:

```ini
Interface: VPN
VPN Type: L2TP over IPSec
```

The default credential defined in the conf file is:

```ini
"L2TPUsername=vpnuser"
"L2TPPassword=passw0rd"
"L2TPSharedKey=SharedSecret"
```

## Tips

1. How to change the IP address of EC2 instance of the Manager stack
   or the Node stack?

    Update the stack with a new value of parameter `EipDomain`, switch the
the value between `vpc` and an empty string ``, this will change the EIP
of the EC2 instance.

    DO NOT operate on the EIP directly, such as allocate a new EIP
and associate it, then release the old. This will cause an error
in locating the original EIP resource when operating on the stack
level.

    Note: Use Lex chatbot to change the IP address of EC2 instance of
    the Node stack.

1. How to enable the HTTPS(SSL certificate) for the Manager stack?

    HTTPS will be enabled by default if you specify a domain for the
    template parameter `SSMDomain`.

    The SSL certificate is issued for the domain `SSMDomain` with AWS
    ACM service, the service is free, there's no charge for the certificates.

## TODO


## Troubleshooting

1. The stack ends up at 'CREATE_FAILED' status.

    Log in the AWS web console, go to CloudFormation, check the event
    list of the stack, found the failed events to locate the root reason,
    check the event list of the nested stack if necessary.

1. For any problem related with the repoes that aws-cfn-vpn depends
on, check with the depended repoes, here is the quick dial of star
gates.

   1. [aws-cfn-vpc](https://github.com/alexzhangs/aws-cfn-vpc)
   1. [aws-cfn-vpc-peer-accepter](https://github.com/alexzhangs/aws-cfn-vpc-peer-accepter)
   1. [aws-cfn-vpc-peer-requester](https://github.com/alexzhangs/aws-cfn-vpc-peer-requester)
   1. [aws-cfn-config-provider](https://github.com/alexzhangs/aws-cfn-config-provider)
   1. [aws-cfn-vpn-lexbot](https://github.com/alexzhangs/aws-cfn-vpn-lexbot)
   1. [aws-cfn-acm](https://github.com/alexzhangs/aws-cfn-acm)
   1. [aws-ec2-shadowsocks-libev](https://github.com/alexzhangs/aws-ec2-shadowsocks-libev)
   1. [shadowsocks-manager](https://github.com/alexzhangs/shadowsocks-manager)
   1. [aws-ec2-ses](https://github.com/alexzhangs/aws-ec2-ses)
   1. [aws-ec2-xl2tpd](https://github.com/alexzhangs/aws-ec2-xl2tpd)
   1. [chap-manager](https://github.com/alexzhangs/chap-manager)
   1. [aws-ec2-supervisor](https://github.com/alexzhangs/aws-ec2-supervisor)
   1. [supervisord](https://github.com/alexzhangs/supervisord)

1. Failed to delete the manager stack.

   If VPC peer connections exist in the manager stacks, deleting the stacks will fail.

   Solution:

   Manually delete all existing peer connections belong to that stack first. This can be done with AWS web console, or the CLI:

   ```sh
   $ aws ec2 describe-vpc-peering-connections
   $ aws ec2 delete-vpc-peering-connection --vpc-peering-connection-id <peering-connection-id>
   ```

1. Encountering errors while executing EC2 userdata.

   This might be caused by using the untested AWS AMI.
   The EC2 userdata is tested only with the AMI listed in the template.

   ```json
   "Mappings": {
     "RegionMap": {
       "ap-east-1": {
         "endpoint": "rds.ap-east-1.amazonaws.com",
         "location": "Asia Pacific (Hong Kong)"
       },
       "ap-northeast-1": {
         "AMI": "ami-29160d47",
         "endpoint": "rds.ap-northeast-1.amazonaws.com",
         "location": "Asia Pacific (Tokyo)"
       },
       ...
     }
   }
   ```

   For the regions without an AMI, you need to figure it out by yourself. Usually, an AWS AMI with which the template works will look like:

   ```
   Amazon Linux AMI 2018.03.0 (HVM), SSD Volume Type
   Amazon Linux 2 AMI (HVM), SSD Volume Type
   ```

   Feel free to open pull requests for the verified compatible AMIs.
