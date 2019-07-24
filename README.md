# aws-cfn-vpn

AWS CloudFormation Stack for VPN services.

This Repo use AWS CloudFormation to automate the deployment of several
VPN services, and is trying to make the deployment as easier as possible.

Additionally, it's also deploying
[shadowsocks-manager](https://github.com/alexzhangs/shadowsocks-manager)
which is a web based node and user management of Shadowsocks.

Below is the VPN services list:

* Shadowsocks-libev, multi nodes with a center user management is supported by deploying this stack
  multi times.
* XL2TPD, the user management is saperate from shadowsocks-manager.

This stack leverages several other repoes to achieve the work, below
gives an overview of the inside dependency structure. All the internal
dependencies will be installed automatically except `aws-ec2-ses`.

```
aws-cfn-vpn (github)
├── aws-cfn-vpc (github)
├── aws-cfn-vpc-peer-accepter (github)
├── aws-cfn-vpc-peer-requester (github)
├── aws-ec2-shadowsocks-libev (github)
│   └── shadowsocks-libev (yum)
├── shadowsocks-manager (github)
│   └── [aws-ec2-ses (github, manually setup involved)]
├── aws-ec2-xl2tpd (github)
│   ├── openswan (yum)
│   └── xl2tpd (yum)
└── chap-manager (github)
```

## Insight

### stack.json

This repo contains a standard AWS CloudFormation template `stack.json`
which can be deployed with AWS web console, AWS CLI or any other AWS
CloudFormation compitable tool.

This template will create an AWS CloudFormation stack, including
following resources:

* 1 nested VPC stack. For details check [aws-cfn-vpc](https://github.com/alexzhangs/aws-cfn-vpc).

* 1 nested VPC peer accepter stack,  accepting VPC peer connection request from
another VPC. For details check
[aws-cfn-vpc-accepter](https://github.com/alexzhangs/aws-cfn-vpc-accepter).

* 1 nested VPC peer requester stack, creating and sending VPC peer connection to
the accepter. For the details  check
[aws-cfn-vpc-requester](https://github.com/alexzhangs/aws-cfn-vpc-requester).

* 1 Security Group.

* 1 EC2 instance. Shadowsocks-libev and/or shadowsocks-manager and/or
L2TPD will be installed depends on your configuration.

For the input parameters and the detail of the template, please check the template
file.

### sample-*.conf

`sample-*.conf` is a config file for stack.json, it's used by
`aws-cfn-deploy` which belongs to an AWS toolkit
[xsh-lib-aws](https://github.com/alexzhangs/xsh-lib-aws), to automate AWS
CloudFormation template deployment.

## Classic Usage

The classic scenario is:

* First, deploy a center stack with Shadowsocks node, shadowsocks-manager
and XL2TPD enabled.

* Second, deploy one or more stack with Shadowsocks node enabled
only. There are 2 different type of deployments you may want to apply:

    1. Deploy multi nodes in the same AWS Region, in different AWS
    accounts.
    This method allows you to balance the network traffic between AWS accounts.

    1. Deploy multi nodes in different AWS Regions, either in the same AWS
    account or in different AWS accounts.
    This method gives you the ability to access to VPN node in different
    geography locations.

    You may also combine the 2 methods above together to gain both
avantages and still have a single center user management of
Shadowsocks, this requires more complex DNS records design.

## Domain Name Design

If you are deploying only 1 node for Shadowsocks, shadowsocks-manager
and XL2TPD, then 1 domain name with 1 DNS record will work for all
services above.

If you are deploying multi nodes, then you may have to give at least 3
domain names.

1. With the method 1 above, 3 domain names needed.

    1. One domain name such as `ss.yourdomain.com` should point to the
    public IPs of all shadowsocks nodes.

    1. The second domain name such as `admin.ss.yourdomain.com` should
    point to the public IP of the shadowsocks-manager node.

    1. The third domain name such as `vpn.yourdomain.com` should
    point to the public IP of the XL2TPD node.

1. With the method 2 above, 3+ domain name needed.

    You need to give a standalone domain name for each Shadowsocks
    node, since balancing on different AWS Regions makes no sense.

## Deployment

Two ways to deploy:

1. Deploy the stack manually with AWS web console or CLI.
1. Deploy the stack with `aws-cfn-deploy` of AWS toolkit
[xsh-lib-aws](https://github.com/alexzhangs/xsh-lib-aws).

NOTE: In either way, you must create IAM user or role to deploy the
stack, you can not use AWS root user or its access key to do the
deployment. Because there is IAM assume role inside the template,
which assumes an action `ec2:AcceptVpcPeeringConnection` and AWS
restricts it's can't be assumed by root user. Otherwise an error would
be found in the events of stack while deployment.

```
"ResourceStatus": "CREATE_FAILED",
"ResourceType": "AWS::EC2::VPCPeeringConnection",
"ResourceStatusReason": "API: ec2:AcceptVpcPeeringConnection Roles may not be assumed by root accounts"
```

### Manually Deployment

You will have to handle the input parameters of the stack, and the
upload of the templates.

### Deploy with `aws-cfn-deploy`

This guide shows how to deploy multi Shadowsocks nodes(3) in the
method 2 above.

TODO: Release `xsh` and `xsh-lib-aws` out.

#### Install xsh-lib-aws

TODO

#### Install aws-cli

TODO

#### Prepare AWS Accounts

1. Create 3 AWS accounts in the web if don't have.

1. Create access key in the AWS web console for each account and add it as a profile.

1. Create EC2 key pair for each account and save it to ~/.ssh.

1. Create IAM user and give admin permissions for each account.

    ```
    aws iam create-user --user-name admin
    aws iam attach-user-policy --user-name admin --policy-arn "arn:aws:iam::aws:policy/AdministratorAccess"
    ```

1. Create access key for each  IAM user.

    ```
    aws iam create-access-key --user-name admin
    aws configure --profile=<your_profile>
    ```

#### Get the code

In the same directory:

```
git clone https://github.com/alexzhangs/aws-cfn-vpn
git clone https://github.com/alexzhangs/aws-cfn-vpc
git clone https://github.com/alexzhangs/aws-cfn-vpc-peer-accepter
git clone https://github.com/alexzhangs/aws-cfn-vpc-peer-requester
```

#### Create the Manager Stack

1. Edit `sample-ssm-and-ssn-0.conf`.

    Replace the values wrapped by '<>' with your prefered.

    ```
    "KeyPairName=<your_aws_ec2_key_pair_name>"
    "SSDomain=<vpn.yourdomain.com>"
    "SSMDomain=<vpn-admin.yourdomain.com>"
    "SSMAdminEmail=<admin@vpn.yourdomain.com>"
    ```
    
    Change any other settings as you want.

1. Active your first AWS account profile.

1. Create the manager stack.

    Run below command at your local:

    ```
    aws-cfn-deploy -b ./aws-cfn-vpn -t stack.json -c sample-ssm-and-ssn-0.conf
    ```

    Then wait the stack creation complete.

    If the stack creation complete successfully, run below command to get the
    output of the stack. Replace `<stack_name>` with the real stack name.

    ```
    aws-cfn-desc <stack_name>
    ```

1. Verify the manage stack deployment.

    Open your browser, visit `http://<PUBLIC_IP>/admin`, a login
    screen should show up.

    Log in with the default username and password if you didn't change
    it in sample conf file.

    ```
    "SSMAdminUsername=admin"
    "SSMAdminPassword=passw0rd"
    ```

#### Create the Node Stack

1. Edit `sample-ssn-1.conf`.

    Set below values by the output of the manager stack.

    ```
    "VpcPeerAccepterVpcId=<your_accepter_vpc_id>"
    "VpcPeerAccepterRoleArn=<your_rolearn_of_accepter_stack>"
    "VpcPeerAccepterSqsQueueUrl=<your_sqs_queue_url_of_accepter_stack>"
    ```
    
    Replace the values wrapped by '<>' with your prefered.

    ```
    "KeyPairName=<your_aws_ec2_key_pair_name>"
    "VpcPeerAccepterRegion=<your_accepter_region>"
    "VpcPeerAccepterAccountId=<your_aws_account_id_of_owner_of_accepter>"
    "SSDomain=<vpn.yourdomain.com>"
    ```

    Change any other settings as you want.

1. Active your sencond AWS profile.

1. Create the node stack.

    Run below command at your local:

    ```
    aws-cfn-deploy -b ./aws-cfn-vpn -t stack.json -c sample-ssn-1.conf
    ```

    Then wait the stack creation complete.

1. If everything goes fine, repeat the same steps with
`sample-ssn-2.conf` to deploy the next node stack.

## Maintain DNS Records

1. Add the public IPs of all nodes including the manage node as `A
record`, such as `ss.yourdomain.com`.

1. Add the public IP of manage node as `A record`, such as `admin.ss.aiview.com`.
 
1. Add the public IP of XL2TPD node as `A record`, such as `vpn.aiview.com`.

## Configure shadowsocks-manager

### Add the Nodes to shadowsocks-manager

1. Log in the shadowsocks-manager web console back with
`admin.ss.aiview.com` after the DNS records get effective.

1. Goto `Home › Shadowsocks › Shadowsocks Nodes › Add Shadowsocks
Node`, add a Shadowsocks node for each node stack you have created.

    NOTE: For the Shadowsocks node created with the sample conf files, the
    property `SHADOWSOCKS MANAGERS › INTERFACE` should choose
    `Private` from the list since following setting is set in the conf file.

    ```
    "SSManagerInterface=2" # 1: Localhost, 2: Private, 3: Public.
    ```

    NOTE: For the Shadowsocks node in manage stack, you don't need to add it by
    yourself. It should have been added as a node already.

### What to do next?

Now you are ready to create Shadowsocks accounts in the web console.
Or import the previously expoted accounts back.

## Verify XL2TPD services

Use your XL2TPD client to connect to the service.

With macOS High Sierra, you can choose the built-in XL2TPD client:

```
Interface: VPN
VPN Type: L2TP over IPSec
```

The default credentials defined in the conf file is:

```
"L2TPUsername=vpnuser"
"L2TPPassword=passw0rd"
"L2TPSharedKey=SharedSecret"
```
