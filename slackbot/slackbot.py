from flask import Flask
from flask import request, redirect
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import subprocess
import re
import validators
import json
from threading import Thread
import requests
import base64

app = Flask(__name__)

# A quick and dirty slack bot to act as a slack insterface to interact with a cluster with
# https://github.com/rawagner/cluster-templates-operator running on it.
# It is meant as a proof of concept and demo, not as something which should actually be used.

# dependencies:
# pip install flask
# pip install Flask-HTTPAuth

# usage: 
# run oc login to the server, on which the templates are configured
# than run startServer.sh

def get_name(entity):
    return entity['metadata']['name']

def get_status(entity):
    if 'status' in entity:
        status = entity['status']
        if 'phase' in status:
            return status['phase']

    return ''

def load_templates():
    return json.loads(subprocess.check_output(['oc', 'get', 'clustertemplates', '-o', 'json']).decode("utf-8").strip())

def load_instances():
    return json.loads(subprocess.check_output(['oc', 'get', 'clustertemplateinstances', '-n', 'slackbot-ns', '-o', 'json']).decode("utf-8").strip())

@app.route('/about', methods=['POST'])
def about():
    return 'Hello world'

@app.route('/list-templates', methods=['POST'])
def list_templates():
    def bg_list_templates(response_url):
        res = 'List of templates: ' + ','.join([get_name(template) for template in load_templates()['items']])

        payload = {"text": res,
                    "username": "CaaS"}
        requests.post(response_url,data=json.dumps(payload))   

    response_url = request.form.get("response_url")
    thr = Thread(target=bg_list_templates, args=[response_url])
    thr.start()
    return "Looking for templates..."


@app.route('/list-clusters', methods=['POST'])
def list_instances():
    def bg_list_instances(response_url):
        res = 'List of clusters: \n' + '\n'.join([get_name(cti) + ': ' + get_status(cti) for cti in load_instances()['items']])
        payload = {"text": res,
                    "username": "CaaS"}
        requests.post(response_url,data=json.dumps(payload))   

    response_url = request.form.get("response_url")
    thr = Thread(target=bg_list_instances, args=[response_url])
    thr.start()
    return "Looking for clusters..."

@app.route('/get-credentials', methods=['POST'])
def get_credentials():
    params = request.form.get('text').split()
    if len(params) != 1:
        return 'Exactly one parameter expected. Example /get-credentials my-cluster-name'

    def bg_list_instances(cluster_name, response_url):
        instance = json.loads(subprocess.check_output(['oc', 'get', 'clustertemplateinstance', cluster_name, '-n', 'slackbot-ns', '-o', 'json']).decode("utf-8").strip())
        if get_status(instance) != 'Ready':
            payload = {"text": 'The cluster is not yet ready, can not give credentials',
                    "username": "CaaS"}
            requests.post(response_url,data=json.dumps(payload))
        else:
            apiserver = instance['status']['apiServerURL']
            secret = json.loads(subprocess.check_output(['oc', 'get', 'secret', cluster_name + '-admin-password', '-n', 'slackbot-ns', '-o', 'json']).decode("utf-8").strip())
            pwd = secret['data']['password']
            base64_message = pwd
            base64_bytes = base64_message.encode('ascii')
            message_bytes = base64.b64decode(base64_bytes)
            pwd_clean = message_bytes.decode('ascii')
            login_command = f'oc login -u kubeadmin -p {pwd_clean} --server {apiserver}'
            payload = {"text": "login command:\n" + login_command}
            requests.post(response_url,data=json.dumps(payload))

    response_url = request.form.get("response_url")
    thr = Thread(target=bg_list_instances, args=[params[0], response_url])
    thr.start()


    return 'Getting credentials...'

@app.route('/deploy', methods=['POST'])
def deploy():
    def bg_list_instances(template_name, cluster_name, response_url):
        oci = f"""
apiVersion: clustertemplate.openshift.io/v1alpha1
kind: ClusterTemplateInstance
metadata:
  namespace: slackbot-ns
  name: {cluster_name}
spec:
  clusterTemplateRef: {template_name}
"""

        f = open("/tmp/f.yaml", "w")
        f.write(oci)
        f.close()
        subprocess.check_output(['oc', 'apply', '-f', '/tmp/f.yaml'])

        payload = {"text": 'request to create a new cluster submitted',
                    "username": "CaaS"}
        requests.post(response_url,data=json.dumps(payload))   


    params = request.form.get('text').split()
    if len(params) != 2:
        return 'Exactly two params expected. First is the name of the cluster template, second the name of the cluster. For example /deploy some-template my-cluster'

    template_name = params[0]
    cluster_name = params[1]
    
    response_url = request.form.get("response_url")
    thr = Thread(target=bg_list_instances, args=[template_name, cluster_name, response_url])
    thr.start()
    return f'Starting deploy cluster {cluster_name} from template {template_name}...'
