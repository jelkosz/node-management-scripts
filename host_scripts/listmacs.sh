#!/bin/sh

for i in `virsh list --all --name`; do echo $i; virsh domiflist $i; done
