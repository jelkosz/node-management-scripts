#!/bin/bash

for vmname in "$@"
do
    echo "deleting $vmname"
    virsh destroy "$vmname" && virsh undefine "$vmname" --remove-all-storage
    echo "deleted $vmname"
done

