# aws-cfn-vpn

AWS CloudFormation Stack for VPN server.

## Dependencies

All dependencies will be installed automaticaslly.
Here gives an overview of the dependencies.

```
aws-cfn-vpn (github)
├── aws-cfn-vpc (github)
├── aws-ec2-shadowsocks-libev (github)
│   └── shadowsocks-libev (yum)
├── shadowsocks-manager (github)
│   └── [aws-ec2-ses (github, manually setup involved)]
├── aws-ec2-xl2tpd (github)
│   ├── openswan (yum)
│   └── xl2tpd (yum)
└── chap-manager (github)
```
