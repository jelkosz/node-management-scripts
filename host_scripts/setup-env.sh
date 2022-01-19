#! /usr/bin/env bash

# This script has been written by https://github.com/jkilzi
# I have just added support for passing num of nodes from outside.
# Next step is to contribute this support back to upstream

set -eu

COMMAND="$0"
TRUE=0
FALSE=1

ISO_FILE=""
CLUSTER_NAME="$(date +%Y-%m-%d_%H-%M)-$(mktemp -uq XXXXXXXX)"
DEBUG=$FALSE

MASTER_DISKGIB=${MASTER_DISKGIB:-20}
MASTER_MEMMIB=${MASTER_MEMMIB:-16}
MASTER_CPUS=${MASTER_CPUS:-4}

WORKER_DISKGIB=${WORKER_DISKGIB:-20}
WORKER_MEMMIB=${WORKER_MEMMIB:-8}
WORKER_CPUS=${WORKER_CPUS:-2}

function usage {
  cat << EOS
Description:
  Creates virtual machines to serve as master and worker hosts in an OpenShift BareMetal cluster installation.
Usage:
  ${COMMAND} <discovery-iso-file> [FLAGS...] 
  
  FLAGS:
    -h | --help                     Displays this help and exits.
    -d | --debug                    Displays debug information.
    -n | --num-of-nodes             Number of masters to create
    -w | --with-workers             By default this command will create only 3 master
                                    hosts unless this flag is passed. In which case 2
                                    additional worker hosts will be created.
                                    Each master host will have:
                                      ${MASTER_CPUS} vCPU, ${MASTER_MEMMIB}GB RAM and ${MASTER_DISKGIB}GB disk
                                    Each worker host will have:
                                      ${WORKER_CPUS} vCPU, ${WORKER_MEMMIB}GB RAM and ${WORKER_DISKGIB}GB disk
    -c | --cluster-name=<string>    The cluster name, this is used in order to
                                    identify to which cluster each vm belongs.
EOS
}

function create_host {
  local NAME=${1:-"$CLUSTER_NAME"}
  local DISKGIB=121
  local MEMMIB=33
  local CPUS=8
  local POOL=default

  if [[ $DEBUG -eq $TRUE ]]
  then
    echo \
      name="$NAME" \
      cdrom="$ISO_FILE" \
      vcpus="$CPUS" \
      ram=$((MEMMIB * 1024)) \
      disk=size="$DISKGIB",pool="$POOL"
  fi

  virt-install \
    --name="$NAME" \
    --cdrom="$ISO_FILE" \
    --vcpus="$CPUS" \
    --boot machine=q35 \
    --boot cdrom,fd,hd \
    --ram=$((MEMMIB * 1024)) \
    --disk=size="$DISKGIB",pool="$POOL" \
    --os-variant=rhel-unknown \
    --network=network=default,bridge=virbr0,model=virtio \
    --graphics=spice \
    --noautoconsole
}

function create_masters {
  local N=$1

  for i in $(seq "$N")
  do
    create_host "$CLUSTER_NAME-$i" $((MASTER_DISKGIB + i)) "$MASTER_MEMMIB" "$MASTER_CPUS"
  done
}

function create_workers {
  local N=$1

  for i in $(seq "$N")
  do
    create_host "$CLUSTER_NAME-worker-$i" $((WORKER_DISKGIB + i)) "$WORKER_MEMMIB" "$WORKER_CPUS"
  done
}

function main {
  local WITH_WORKERS=$FALSE
  local NUM_OF_NODES=3
  
  if [[ -z "$*" ]]
  then
    usage
    exit
  fi
  
  for i in "$@"
  do
    case $i in
        -c=* | --cluster-name=*)
          CLUSTER_NAME="${i#*=}-$CLUSTER_NAME"
          ;;
	-n=* | --num-of-nodes=*)
          NUM_OF_NODES="${i#*=}"
          ;;
        -w | --with-workers)
          WITH_WORKERS=$TRUE
          ;;
        -d | --debug)
          DEBUG=$TRUE
          ;;
        -h | --help)
          usage
          exit
          ;;
        *)
          if [[ -f "${i#*=}" && -r "${i#*=}" ]]
          then
            ISO_FILE="${i#*=}"
          else
            echo "The file specified "${i#*=}" could not be found or is not readable."
            exit 1
          fi
          ;;
    esac  
  done

  if [[ $DEBUG -eq $TRUE ]]
  then
    echo "CLUSTER_NAME=$CLUSTER_NAME"
    echo "ISO_FILE=$ISO_FILE"
    echo "WITH_WORKERS=$WITH_WORKERS"
    echo "NUM_OF_NODES=$NUM_OF_NODES"
  fi
  create_masters $NUM_OF_NODES
  [[ $WITH_WORKERS -eq $TRUE ]] && create_workers 2
}

main "$@"
