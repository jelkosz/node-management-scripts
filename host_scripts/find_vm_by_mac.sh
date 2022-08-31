#!/bin/bash

virsh list --all --name \
    | while read line; do ( \
        virsh domiflist $line 2> /dev/null \
        | sed 's,^,'$line': ,' \
    ); done | grep $1 | awk '{print $1}' | head -c -2
