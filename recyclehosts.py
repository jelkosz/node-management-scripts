import subprocess
import json
import random
import string
import time
import sys

def load_agents(ns):
    return json.loads(subprocess.check_output(['oc', 'get', 'agents', '-n', ns, '-o', 'json']).decode("utf-8").strip())

def get_agent_name(agent):
    return agent['metadata']['name']

def get_unbinding_agents(agents):
    def agent_unbinding(agent):
        return agent['status']['debugInfo']['state'] == 'unbinding-pending-user-action'

    def get_first_mac_from_agent(agent):
        interfaces = agent['status']['inventory']['interfaces']
        if type(interfaces) is list and len(interfaces) > 0:
            return interfaces[0]['macAddress']
        return None
    
    return [(get_agent_name(agent), get_first_mac_from_agent(agent)) for agent in agents['items'] if agent_unbinding(agent)]

def create_fresh_vms(names_to_mac, ns):
    def get_iso_url(ns):
        # this assumes there is one infra env in the ns. Its a quick and dirty PoC to see if this approach is even viable. 
        infraenv = json.loads(subprocess.check_output(['oc', 'get', 'infraenvs', '-n', ns, '-o', 'json']).decode("utf-8").strip())
        return infraenv['items'][0]['status']['isoDownloadURL']

    if len(unbinding_agents) == 0:
        return
    iso_url = get_iso_url(ns)
    subprocess.Popen(['./host_scripts/create_vms_from_iso_path.sh', iso_url, str(len(names_to_mac)), 'refresher'])

def approve_and_rename_agents(agents, ns):
    def generate_random_hostname():
        letters = string.ascii_lowercase
        return ''.join(random.choice(letters) for i in range(30))

    def agent_needs_patch(agent):
        # not completely correct, the user might set deliberately the hostname wrong and it would not be handled here
        return agent['spec']['approved'] == False or 'hostname' not in agent['spec']

    agents_need_patch = [get_agent_name(agent) for agent in agents['items'] if agent_needs_patch(agent)]
    for agent_needs_patch in agents_need_patch:
        patch = '{"spec": {"approved": true, "hostname": "' + generate_random_hostname() + '"}}'
        subprocess.Popen(['oc', 'patch', 'agent', agent_needs_patch, '-n', ns, '-p', patch, '--type', 'merge'])

def delete_old_vms(names_to_mac):
    def get_virshname_from_mac(mac):
        return subprocess.check_output(['./host_scripts/find_vm_by_mac.sh', mac]).decode("utf-8").strip()

    virshnames = [name for name in [get_virshname_from_mac(name_to_mac[1]) for name_to_mac in names_to_mac] if name]
    subprocess.run(['./host_scripts/delete_vms.sh'] + virshnames)

def delete_old_agents(names_to_mac, ns):
    names = [name_to_mac[0] for name_to_mac in names_to_mac]
    for name in names:
        subprocess.Popen(['oc', 'delete', 'agent', name, '-n', ns])

def get_namespace():
    if len(sys.argv) == 1:
        exit("Please provide the namespace to recycle hosts in")
    elif len(sys.argv) > 2:
        exit("Exactly one argument expected, the namespace to recycle the hosts in")
    else:
        return sys.argv[1]

if __name__ == "__main__":
    ns = get_namespace()

    while True:
        agents = load_agents(ns)
        # a list of tuples (agent name -> mac address)
        unbinding_agents = get_unbinding_agents(agents)

        approve_and_rename_agents(agents, ns)
        create_fresh_vms(unbinding_agents, ns)
        delete_old_vms(unbinding_agents)
        delete_old_agents(unbinding_agents, ns)

        time.sleep(10)

