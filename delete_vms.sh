#!/bin/bash

for vmname in "$@"
do
    echo "deleting $vmname"
    virsh destroy "$vmname" && virsh undefine "$vmname"
    echo "deleted $vmname"
done

