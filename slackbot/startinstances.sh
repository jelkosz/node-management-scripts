#!/bin/bash

VMS=`aws ec2 describe-instances --region us-east-1 --filters "Name=tag:Name,Values=$1*" --output text --query 'Reservations[*].Instances[*].InstanceId' | tr '\n' ' '`
aws ec2 start-instances --region us-east-1 --instance-id $VMS
