# dependencies:
# pip install flask
# pip install Flask-HTTPAuth
# pip install kubernetes

from flask import Flask
from flask import request, redirect
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import re
import validators
import json
from threading import Thread
import requests
import base64
import hmac
import hashlib
import time
import kubernetes
from kubernetes import config, client
from kubernetes.client.rest import ApiException
from pprint import pprint

app = Flask(__name__)

# init kubernetes connction
config.load_kube_config(config_file='/root/.kube/cluster-templates')
api_client = client.ApiClient()
api_instance = client.CustomObjectsApi(api_client)
core_api_instance = client.CoreV1Api()
user_namespace = 'clusters'

group = 'clustertemplate.openshift.io'
version = 'v1alpha1'
pretty = 'true'
limit = 56
watch = False

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

# https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/CustomObjectsApi.md
def create_crd(body, namespace, plural):
    try:
        api_instance.create_namespaced_custom_object(group, version, namespace, plural, body, pretty=pretty)
    except ApiException as e:
        print("Exception when calling CustomObjectsApi->create_namespaced_custom_object: %s\n" % e)

def delete_cti(name):
    try:
        api_instance.delete_namespaced_custom_object(group, version, user_namespace, 'clustertemplateinstances', name)
    except ApiException as e:
        print("Exception when calling CustomObjectsApi->delete_namespaced_custom_object %s\n" % e)

def load_crd(crd_plural, name = None):
    try:
        if name is None:
            return api_instance.list_cluster_custom_object(group, version, crd_plural, pretty=pretty, limit=limit, watch=watch)
        return api_instance.get_namespaced_custom_object(group, version, user_namespace, crd_plural, name)
    except ApiException as e:
        print("Exception when calling CustomObjectsApi->list_cluster_custom_object: %s\n" % e)

def load_templates():
    return load_crd('clustertemplates')

def load_instances(name = None):
    return load_crd('clustertemplateinstances', name)

def load_quota():
    return load_crd('clustertemplatequotas')

def load_secret(name):
    try:
        return core_api_instance.read_namespaced_secret(name, user_namespace).data
    except ApiException as e:
        print("Exception when getting secret: %s\n" % e)

@app.route('/about', methods=['POST'])
def about():
    validation_error = verify_client_signature(request)
    if validation_error is not None:
        return validation_error

    return 'Welome to the cluster as a service slackbot! \n • You can start by checking what clusters has already been deployed by typing `/list-clusters` \n • If you wish to explore what clusters you could deploy, please type `/list-templates`\nHave fun!'

@app.route('/list-templates', methods=['POST'])
def list_templates():
    validation_error = verify_client_signature(request)
    if validation_error is not None:
        return validation_error

    def to_printable_template(template, quota_parsed):
        template_name = get_name(template)
        if template_name not in quota_parsed:
            return '*' + template_name + '*: exists but is not allowed to be used'

        if quota_parsed[template_name]['allowed'] == '-1':
            return '*' + template_name + '*: no restrictions, make as much as you want!'

        return '*' + get_name(template) + '* allowed: ' + quota_parsed[template_name]['allowed'] + ' already used: ' + quota_parsed[template_name]['used'] 

    def bg_list_templates(response_url):
        # expecting that there is always exactly one quota in the namespace
        # by definition there cant be more than one
        # on the other hand there can be 0 which means that all templates are allowed. Ignoring this case for now
        quota = load_quota()['items'][0]
        quota_parsed = {}
        for allowed_template in quota['spec']['allowedTemplates']:
            allowed_count = -1
            if 'count' in allowed_template:
                allowed_count = allowed_template['count']

            quota_parsed[allowed_template['name']] = {'allowed': str(allowed_count), 'used': str(0)}

        for used_template in quota['status']['templateInstances']:
            if 'count' in used_template:
                quota_parsed[used_template['name']]['used'] = str(used_template['count'])


        res = 'List of templates: \n' + ''.join(['• ' + to_printable_template(template, quota_parsed) + '\n' for template in load_templates()['items']]) + '\nIn order to deploy a cluster from one, run `/deploy <template name> <cluster name>`'

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
        instance = load_instances(cluster_name)

        if instance is None:
            payload = {"text": 'Can not find cluster with name ' + cluster_name,
                    "username": "CaaS"}
            requests.post(response_url,data=json.dumps(payload))
        elif get_status(instance) != 'Ready':
            payload = {"text": 'The cluster is not yet ready, can not give credentials',
                    "username": "CaaS"}
            requests.post(response_url,data=json.dumps(payload))
        else:
            apiserver = instance['status']['apiServerURL']
            secret = load_secret(cluster_name + '-admin-password')
            pwd = secret['password']
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

    def bg_list_instances(template_name, cluster_name, user_name, u_namespace, response_url):
        cti = {
  "apiVersion": "clustertemplate.openshift.io/v1alpha1",
  "kind": "ClusterTemplateInstance",
  "metadata": {
    "namespace": u_namespace,
    "name": cluster_name,
    "annotations": {
      "slackbot.openshift.io/requester": user_name
    }
  },
  "spec": {
    "clusterTemplateRef": template_name
  }
}
        create_crd(cti, u_namespace, 'clustertemplateinstances')
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
    thr = Thread(target=bg_list_instances, args=[template_name, cluster_name, user_name, user_namespace, response_url])
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
        delete_cti(cluster_name)
        payload = {"text": 'delete initiated',
                    "username": "CaaS"}
        requests.post(response_url,data=json.dumps(payload))

    response_url = request.form.get("response_url")
    thr = Thread(target=bg_delete, args=[cluster_name, response_url])
    thr.start()
    return f'Starting to delete cluster {cluster_name}...'

