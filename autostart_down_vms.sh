#!/bin/bash

while :
do
  for filename in `virsh list --all | grep 'shut off' | awk '{print $2}'` ; do
    virsh start $filename
  done
  sleep 20
done
