#!/bin/bash

URL=$1
NUM_OF_NODES=$2
PREFIX=$3

DOWNLOADED_FILENAME="/tmp/$PREFIX-$(mktemp -uq XXXXXXXX).iso"

wget -O $DOWNLOADED_FILENAME ''$URL'' --no-check-certificate >> /tmp/vmrunner.log 

./host_scripts/setup-env.sh $DOWNLOADED_FILENAME --num-of-nodes=$NUM_OF_NODES --cluster-name=$PREFIX -d &>> /tmp/vmrunner.log

echo "installation DONE" >> /tmp/vmrunner.log
