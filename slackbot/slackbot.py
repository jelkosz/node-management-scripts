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
import hmac
import hashlib
import time

app = Flask(__name__)

# dependencies:
# pip install flask
# pip install Flask-HTTPAuth


# checks if the request actually came from the correct slack client or its an attack
def verify_client_signature(request):
    # mostly taken from: https://api.slack.com/authentication/verifying-requests-from-slack#signing_secrets_admin_page
    
    slack_signing_secret=''
    with open('slack_secret') as f:
        slack_signing_secret = f.readline().strip()
    request_body = request.get_data().decode('utf-8')
    timestamp = request.headers['X-Slack-Request-Timestamp']
    if float(time.time()) - float(timestamp) > 60 * 5:
        # The request timestamp is more than five minutes from local time.
        # It could be a replay attack, so let's ignore it.
        return 'Looks like a replay attack, rejecting'
    sig_basestring = 'v0:' + timestamp + ':' + request_body

    my_signature = 'v0=' + hmac.new(bytes(slack_signing_secret , 'utf-8'), 
            msg = bytes(sig_basestring , 'utf-8'), 
            digestmod = hashlib.sha256).hexdigest()

    slack_signature = request.headers['X-Slack-Signature']
    if hmac.compare_digest(my_signature, slack_signature):
        return None

    return 'Not an authorized client, rejecting request'

def verify_request(request):
    return verify_client_signature(request)

def get_name(entity):
    return entity['metadata']['name']

def get_status(entity):
    if 'status' in entity:
        status = entity['status']
        if 'phase' in status:
            return status['phase']

    return ''

def load_templates():
    return json.loads(subprocess.check_output(['oc', '--kubeconfig', '/root/.kube/cluster-templates', 'get', 'clustertemplates', '-o', 'json']).decode("utf-8").strip())

def load_instances():
    return json.loads(subprocess.check_output(['oc', '--kubeconfig', '/root/.kube/cluster-templates', 'get', 'clustertemplateinstances', '-n', 'slackbot-ns', '-o', 'json']).decode("utf-8").strip())


@app.route('/about', methods=['POST'])
def about():
    validation_error = verify_request(request)
    if validation_error is not None:
        return validation_error
    
    return 'This is the about message'

@app.route('/list-templates', methods=['POST'])
def list_templates():
    validation_error = verify_request(request)
    if validation_error is not None:
        return validation_error

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
    validation_error = verify_request(request)
    if validation_error is not None:
        return validation_error

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
    validation_error = verify_request(request)
    if validation_error is not None:
        return validation_error

    params = request.form.get('text').split()
    if len(params) != 1:
        return 'Exactly one parameter expected. Example /get-credentials my-cluster-name'

    def bg_list_instances(cluster_name, response_url):
        instance = json.loads(subprocess.check_output(['oc', '--kubeconfig', '/root/.kube/cluster-templates', 'get', 'clustertemplateinstance', cluster_name, '-n', 'slackbot-ns', '-o', 'json']).decode("utf-8").strip())
        if get_status(instance) != 'Ready':
            payload = {"text": 'The cluster is not yet ready, can not give credentials',
                    "username": "CaaS"}
            requests.post(response_url,data=json.dumps(payload))
        else:
            apiserver = instance['status']['apiServerURL']
            secret = json.loads(subprocess.check_output(['oc', '--kubeconfig', '/root/.kube/cluster-templates', 'get', 'secret', cluster_name + '-admin-password', '-n', 'slackbot-ns', '-o', 'json']).decode("utf-8").strip())
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
    validation_error = verify_request(request)
    if validation_error is not None:
        return validation_error

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
        subprocess.check_output(['oc', '--kubeconfig', '/root/.kube/cluster-templates', 'apply', '-f', '/tmp/f.yaml'])

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