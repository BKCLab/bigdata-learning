#!/bin/bash

cd terraform
terraform init
terraform apply -auto-approve

# Fetch values from Terraform output
datanode1_ip=$(terraform output -raw datanode1_ip)
datanode2_ip=$(terraform output -raw datanode2_ip)
namenode_ip=$(terraform output -raw namenode_ip)

datanode1_private_ip=$(terraform output -raw datanode1_private_ip)
datanode2_private_ip=$(terraform output -raw datanode2_private_ip)
namenode_private_ip=$(terraform output -raw namenode_private_ip)
cd ../ansible
# Create the Ansible inventory file
cat <<EOF > inventory.ini

[namenode]
namenode ansible_host=$namenode_ip private_ip=$namenode_private_ip

[datanodes]
datanode1 ansible_host=$datanode1_ip private_ip=$datanode1_private_ip
datanode2 ansible_host=$datanode2_ip private_ip=$datanode2_private_ip

[all:vars]
ansible_user=root
ansible_ssh_private_key_file=~/.ssh/id_rsa
ansible_ssh_common_args="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
EOF

echo "Ansible inventory written to inventory.ini"

ansible-playbook main.yml --extra-vars "@vars.yml"