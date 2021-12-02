#!/bin/bash

virsh list | sed '/^$/d' | tail -n +3 | awk '{print $2}'
