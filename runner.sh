#!/bin/bash

URL=$1
NUM_OF_NODES=$2

DOWNLOADED_FILENAME="/tmp/from-ui-$(mktemp -uq XXXXXXXX).iso"

wget -O $DOWNLOADED_FILENAME ''$URL'' --no-check-certificate >> /tmp/vmrunner.log 

/root/webapp/setup-env.sh $DOWNLOADED_FILENAME --num-of-nodes=$NUM_OF_NODES -d >> /tmp/vmrunner.log

echo "installation DONE" >> /tmp/vmrunner.log
