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
    # https://api.slack.com/authentication/verifying-requests-from-slack#signing_secrets_admin_page
    
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

def validate_input(*strings):
    def validate_string(to_validate):
        if len(to_validate) > 30:
            return 'Input argument too long. Max length 30, actual: ' + to_validate

        valid = re.match('^[\w-]+$', to_validate) is not None
        if not valid:
            return 'Only alphanumeric values and dashes are allowed, received: ' + to_validate
        return None

    for string in strings:
        err = validate_string(string)
        if err is not None:
            return err

def get_name(entity):
    return entity['metadata']['name']

def get_requester(entity):
    annotations = entity['metadata']['annotations']
    if 'slackbot.openshift.io/requester' in annotations:
        return annotations['slackbot.openshift.io/requester']
    return '<unknown user>'

def get_status(entity):
    if 'status' in entity:
        status = entity['status']
        if 'phase' in status:
            return status['phase']

    return ''

def load_templates():
    return json.loads(subprocess.check_output(['oc', '--kubeconfig', '/root/.kube/cluster-templates', 'get', 'clustertemplates', '-o', 'json']).decode("utf-8").strip())

def load_instances():
    return json.loads(subprocess.check_output(['oc', '--kubeconfig', '/root/.kube/cluster-templates', 'get', 'clustertemplateinstances', '-n', 'default', '-o', 'json']).decode("utf-8").strip())

@app.route('/about', methods=['POST'])
def about():
    validation_error = verify_client_signature(request)
    if validation_error is not None:
        return validation_error

    return 'This is the about message\n • one \n • two'

@app.route('/list-templates', methods=['POST'])
def list_templates():
    validation_error = verify_client_signature(request)
    if validation_error is not None:
        return validation_error

    def bg_list_templates(response_url):
        res = 'List of templates: \n' + ''.join(['• ' + get_name(template) + '\n' for template in load_templates()['items']]) + 'In order to deploy a cluster from one, run `/deploy <template name> <cluster name>`'

        payload = {"text": res,
                    "username": "CaaS"}
        requests.post(response_url,data=json.dumps(payload))   

    response_url = request.form.get("response_url")
    thr = Thread(target=bg_list_templates, args=[response_url])
    thr.start()
    return "Looking for templates..."


@app.route('/list-clusters', methods=['POST'])
def list_instances():
    validation_error = verify_client_signature(request)
    if validation_error is not None:
        return validation_error

    def bg_list_instances(response_url):
        res = 'List of clusters: \n' + ''.join(['• ' + get_name(cti) + ': ' + get_status(cti) + ', requestor: ' + get_requester(cti) + '\n' for cti in load_instances()['items']]) + 'In order to get the credentials for one of them, run `/get-credentials <cluster name>`'
        payload = {"text": res,
                    "username": "CaaS"}
        requests.post(response_url,data=json.dumps(payload))   

    response_url = request.form.get("response_url")
    thr = Thread(target=bg_list_instances, args=[response_url])
    thr.start()
    return "Looking for clusters..."

@app.route('/get-credentials', methods=['POST'])
def get_credentials():
    validation_error = verify_client_signature(request)
    if validation_error is not None:
        return validation_error

    params = request.form.get('text').split()
    if len(params) != 1:
        return 'Exactly one parameter expected. Example /get-credentials my-cluster-name'

    input_err = validate_input(params[0])
    if (input_err) is not None:
        return input_err

    def bg_list_instances(cluster_name, response_url):
        instance = json.loads(subprocess.check_output(['oc', '--kubeconfig', '/root/.kube/cluster-templates', 'get', 'clustertemplateinstance', cluster_name, '-n', 'default', '-o', 'json']).decode("utf-8").strip())
        if get_status(instance) != 'Ready':
            payload = {"text": 'The cluster is not yet ready, can not give credentials',
                    "username": "CaaS"}
            requests.post(response_url,data=json.dumps(payload))
        else:
            apiserver = instance['status']['apiServerURL']
            secret = json.loads(subprocess.check_output(['oc', '--kubeconfig', '/root/.kube/cluster-templates', 'get', 'secret', cluster_name + '-admin-password', '-n', 'default', '-o', 'json']).decode("utf-8").strip())
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
    validation_error = verify_client_signature(request)
    if validation_error is not None:
        return validation_error

    def bg_list_instances(template_name, cluster_name, user_name, response_url):
        oci = f"""
apiVersion: clustertemplate.openshift.io/v1alpha1
kind: ClusterTemplateInstance
metadata:
  namespace: default
  name: {cluster_name}
  annotations:
    slackbot.openshift.io/requester: {user_name}
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
    user_name = request.form.get("user_name")
    
    input_err = validate_input(template_name, cluster_name)
    if (input_err) is not None:
        return input_err

    response_url = request.form.get("response_url")
    thr = Thread(target=bg_list_instances, args=[template_name, cluster_name, user_name, response_url])
    thr.start()
    return f'Starting deploy cluster {cluster_name} from template {template_name}...'

@app.route('/delete', methods=['POST'])
def delete():
    validation_error = verify_client_signature(request)
    if validation_error is not None:
        return validation_error

    params = request.form.get('text').split()
    if len(params) != 1:
        return 'Exactly one parameter expected. Example /get-credentials my-cluster-name'

    cluster_name = params[0]
    input_err = validate_input(cluster_name)
    if (input_err) is not None:
        return input_err

    def bg_delete(cluster_name, response_url):
        subprocess.check_output(['oc', '--kubeconfig', '/root/.kube/cluster-templates', 'delete', 'cti', cluster_name])
        payload = {"text": 'delete initiated',
                    "username": "CaaS"}
        requests.post(response_url,data=json.dumps(payload))

    response_url = request.form.get("response_url")
    thr = Thread(target=bg_delete, args=[cluster_name, response_url])
    thr.start()
    return f'Starting to delete cluster {cluster_name}...'

