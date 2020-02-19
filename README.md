# aws-cfn-vpn

AWS CloudFormation Stack for VPN services.

This Repo use AWS CloudFormation to automate the deployment of Shadowsocks
and XL2TPD, and is trying to make the deployment as easier as possible.

Additionally, it's also deploying
[shadowsocks-manager](https://github.com/alexzhangs/shadowsocks-manager)
which is a web based Shadowsocks management tool for multi user and traffic statistics,
support multi node, sync IPs to name.com.

Below is the VPN services list:

* Shadowsocks-libev, multi nodes with a center user management is supported by deploying this stack
  multi times.
* XL2TPD, the user management is separate from shadowsocks-manager.

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
├── chap-manager (github)
└── aws-ec2-supervisor (github)
```

## Insight

### stack.json

This repo contains a standard AWS CloudFormation template `stack.json`
which can be deployed with AWS web console, AWS CLI or any other AWS
CloudFormation compitable tool.

This template will create an AWS CloudFormation stack, including
following resources:

* 1 nested VPC stack.

    For the details check [aws-cfn-vpc](https://github.com/alexzhangs/aws-cfn-vpc).

* 1 nested VPC peer accepter stack if set EnableVpcPeerAccepter=1.

    It accepts VPC peer connection request from another VPC. VPC peer
connection is used to create private network connection between
manager stack and node stack, to protect the multi-user API from
opening to public internet.

    For the details check
[aws-cfn-vpc-peer-accepter](https://github.com/alexzhangs/aws-cfn-vpc-peer-accepter).

* 1 nested VPC peer requester stack if set EnableVpcPeerRequester=1.

    It sends request to the accepter to create VPC peer connection.

    For the details check
[aws-cfn-vpc-peer-requester](https://github.com/alexzhangs/aws-cfn-vpc-peer-requester).

* 1 EC2 Instance.
    * Shadowsocks-libev is installed if set EnableSSN=1.
    * shadowsocks-manager is installed if set EnableSSM=1.
    * L2TPD is installed if set EnableL2TP=1.

    For the input parameters and the detail of the template, please check the template
file.

### sample-*.conf

`sample-*.conf` are config files used by `aws-cfn-deploy` to automate AWS
CloudFormation template deployment.

`aws-cfn-deploy` can be installed from repo [xsh-lib/aws](https://github.com/xsh-lib/aws).

## Classic Usage

There are 2 classic deployment methods:

1. Deploy a single stack with every inside, including
shadowsocks-manager, Shadosocks node and XL2TPD.
There's a sample config file `sample-ssm-and-ssn-0.conf` for this.

1. Deploy at least 2 stacks, one for shadowsocks-manager and XL2TPD,
one or more for Shadowsocks nodes. Each one needs to be deployed in a
different AWS account. That allows you to balance network triffic between
AWS accounts.
There are 3 sample config files for this.

    * sample-ssm.conf
    * sample-ssn-1.conf
    * sample-ssn-2.conf

## Domain Name Design

There are 3 DNS host names needed for your services:

1. The domain name pointing to shadowsocks-manager service, such
as `admin.ss.yourdomain.com`.

1. The domain name pointing to XL2TPD services, such as
`vpn.yourdomain.com`.

1. The domain name pointing to Shadowsocks nodes, such as
`ss.yourdomain.com`.

If you are deploying a single stack with everything inside, then one
domain host name will work out.

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
upload templates and Lambda function to S3, and handle the parameters
for each nested templates.

### Prepare AWS Accounts

1. Sign up [AWS accounts](https://aws.amanzon.com) if don't have.

    You will need more than one account if planning to deploy multi node stacks.

1. Create an IAM user and give it admin permissions in each AWS account.

    This can be done with AWS CLI if you already have access key
    configured for the account:

    ```sh
    $ aws iam create-user --user-name admin
    $ aws iam attach-user-policy --user-name admin --policy-arn "arn:aws:iam::aws:policy/AdministratorAccess"
    ```

    Otherwise just use the AWS web console.

    NOTE: You must create IAM user or role to deploy the
    stacks, you can not use AWS `root user` or its access key to do the
    deployment. Because there is IAM assume role inside the template,
    which assumes an action `ec2:AcceptVpcPeeringConnection` and AWS
    restricts it's can't be assumed by root user.

1. Create an access key for each IAM user created in last step.

    This can be done with AWS CLI if you already have access key
    configured for the account:

    ```sh
    $ aws iam create-access-key --user-name admin
    ```

    Otherwise just use the AWS web console.

1. Create a profile for each access key created in last step.

   A region is needed to be set in this step.

   ```sh
   $ aws configure --profile=<your_profile_name>
   ```

### Get the code

In the same directory:

```sh
$ git clone https://github.com/alexzhangs/aws-cfn-vpn
$ git clone https://github.com/alexzhangs/aws-cfn-vpc
$ git clone https://github.com/alexzhangs/aws-cfn-vpc-peer-accepter
$ git clone https://github.com/alexzhangs/aws-cfn-vpc-peer-requester
```

### Create the Manager Stack

1. Activate your AWS profile.

   ```bash
   $ xsh aws/cfg/activate <your_profile>
   ```

1. Create an EC2 key pair in AWS and save it to ~/.ssh.

   ```bash
   $ xsh aws/ec2/key/create -f ~/.ssh/<keyname> -m 0377 <keyname>
   ```

1. Edit `sample-ssm.conf`.

    Replace the values wrapped by '<>' with your prefered.

    ```ini
    "KeyPairName=<your_aws_ec2_key_pair_name>"
    "SSMDomain=<vpn-admin.yourdomain.com>"
    "SSMAdminEmail=<admin@vpn.yourdomain.com>"
    ```

    Change any other settings as you wish.

1. Create the manager stack.

    Run below command at your local:

    ```bash
    $ xsh aws/cfn/deploy -C ./aws-cfn-vpn -t stack.json -c sample-ssm.conf
    ```

    Then wait the stack creation complete.

    If the stack creation complete successfully, run below command to get the
    output of the stack. Replace `<stack_name>` with the real stack name.

    ```bash
    $ xsh aws/cfn/stack/desc <stack_name>
    ```

1. Verify the manager stack deployment.

   Open your browser, visit `http://<PUBLIC_IP>/admin`, a login screen should show up.

   Log in with the default username and password if you didn't change it in sample conf file.

   ```ini
   "SSMAdminUsername=admin"
   "SSMAdminPassword=passw0rd"
   ```

### Create the Node Stack

1. Activate another AWS profile and create EC2 key pair.

    Refer to the steps in the last section.

1. Edit `sample-ssn-1.conf`.

    Set below values by the output of the manager stack.

    ```ini
    "VpcPeerAccepterVpcId=<your_accepter_vpc_id>"
    "VpcPeerAccepterRoleArn=<your_rolearn_of_accepter_stack>"
    "VpcPeerAccepterSqsQueueUrl=<your_sqs_queue_url_of_accepter_stack>"
    "SnsTopicArn=<your_snstopicarn_of_ssm_stack>"
    ```

    Replace the values wrapped by '<>' with your prefered.

    ```ini
    "SSDomain=<vpn.yourdomain.com>"
    "KeyPairName=<your_aws_ec2_key_pair_name>"
    "VpcPeerAccepterRegion=<your_accepter_region>"
    "VpcPeerAccepterAccountId=<your_aws_account_id_of_owner_of_accepter>"
    ```

    Change any other settings as you wish.

1. Create the node stack.

    Run below command at your local:

    ```bash
    $ xsh aws/cfn/deploy -C ./aws-cfn-vpn -t stack.json -c sample-ssn-1.conf
    ```

    Then wait the stack creation complete.

1. If everything goes fine, repeat the same steps with
`sample-ssn-2.conf` to deploy the next node stack.

## Maintain DNS Records

1. Create a DNS `A record`, such as `admin.ss`.yourdomain.com,
pointing to the public IP of EC2 Instance of manager stack.

    Use this domain to access to the shadowsocks-manager.

1. Create a DNS `A record`, such as `vpn`.yourdomain.com, pointing to the
public IP of EC2 Instance of manager stack.

    Use this domain to access to the L2TP service.

1. Create a DNS `A record`, such as `ss`.yourdomain.com pointing to
the public IP of EC2 Instance of node stack.

    If you use `name.com` as your Nameserver and have below settings
    before to create node stack, then you can skip this step,
    shadowsocks-manager has taken care of the DNS recorders.

    ```ini
    "SSDomainNameServer=name.com"
    "SSDomainUsername=<your_username_of_name.com>"
    "SSDomainCredential=<your_api_token_of_name.com>"
    ```

    Use this domain to access to the Shadowsocks service.

## Configure shadowsocks-manager

1. Log in the shadowsocks-manager web console back at
`http://admin.ss.yourdomain.com/admin` after the DNS records get
effective.

1. Goto `Home › Shadowsocks › Shadowsocks Nodes › Add Shadowsocks
Node`, to check the node list, all node stacks you created should have been
registered as nodes automatically.

    Note: The registration is rely on the AWS Config, SNS and Lambda services,
it takes up to around 15 minutes to capture and delivery the config changes.

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
value between `vpn` and an empty string ``, this will change the EIP
of the EC2 instance.

DO NOT operate on the EIP directly, such as allocate a new EIP
and associate it, then release the old. This will cause an error
on locating the original EIP resource when operating on the stack
level.


## Troubleshooting

1. The stack ends up at 'CREATE_FAILED' status.

    Log in the AWS web console, go to CloudFormation, check the event
    list of the stack, found the failed events to locate the root
    reason, check the event list of nested stack if neccessary.

1. For any problem related with the repoes that aws-cfn-vpn depends
on, check with the depended repoes, here is the quick dial of star
gates.

   1. [aws-cfn-vpc](https://github.com/alexzhangs/aws-cfn-vpc)
   1. [aws-cfn-vpc-peer-accepter](https://github.com/alexzhangs/aws-cfn-vpc-peer-accepter)
   1. [aws-cfn-vpc-peer-requester](https://github.com/alexzhangs/aws-cfn-vpc-peer-requester)
   1. [aws-ec2-shadowsocks-libev](https://github.com/alexzhangs/aws-ec2-shadowsocks-libev)
   1. [shadowsocks-manager](https://github.com/alexzhangs/shadowsocks-manager)
   1. [aws-ec2-ses](https://github.com/alexzhangs/aws-ec2-ses)
   1. [aws-ec2-xl2tpd](https://github.com/alexzhangs/aws-ec2-xl2tpd)
   1. [chap-manager](https://github.com/alexzhangs/chap-manager)
   1. [aws-ec2-supervisor](https://github.com/alexzhangs/aws-ec2-supervisor)

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

   For the regions without an AMI, you need to figure it out by yourself. Usually an AWS AMI with which the template works, will look like:

   ```
   Amazon Linux AMI 2018.03.0 (HVM), SSD Volume Type
   ```

   Some of Amazon Linux 2 AMIs have been proved not working.
   Feel free to open pull requests for the verified compatible AMIs.
