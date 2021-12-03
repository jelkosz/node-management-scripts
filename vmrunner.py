from flask import Flask
from flask import request, redirect
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import subprocess
import re
import validators

# Dear poor person looking at this code. I apologise.
# --Tomas

# dependencies:
# pip install flask
# pip install Flask-HTTPAuth

app = Flask(__name__)
auth = HTTPBasicAuth()

users = {
}

def init_users():
    with open ("../users", "r") as usersfile:
        users_and_pass = usersfile.readlines()
        for user_and_pass in users_and_pass:
            (user, password) = user_and_pass.strip().split('=')
            users[user] = password

init_users()

@auth.verify_password
def verify_password(username, password):
    if username in users and \
            check_password_hash(users.get(username), password):
        return username

@app.route('/logout', methods=['GET'])
def logout():
    return redirect(f'http://.:.@{request.host}')

@app.route('/', methods=['GET', 'POST'])
@auth.login_required
def create_vms():

    def get_running_vms():
        vm_list = subprocess.check_output(['./get_running_vms.sh']).decode("utf-8").strip().split()
        return f'{len(vm_list)} VMs running. <a href="/manage">Manage</a>'

    def get_status():
        wget = subprocess.check_output(['./get_running_process_count.py', 'wget']).decode("utf-8").strip()
        virt_install = subprocess.check_output(['./get_running_process_count.py', 'virt-install']).decode("utf-8").strip()

        if wget != "2":
            return "<div>An image is being downloaded</div>"
        elif virt_install != "2":
            return "<div>The VM(s) are being created</div> <br/>"
        return ""

    def start_vms_on_background(url, num_of_nodes, prefix):
        subprocess.Popen(['./runner.sh', url, num_of_nodes, prefix])

    refresher = """
        <head>
            <title>Node Creator 4000</title>
            <meta http-equiv="refresh" content="5">
        </head>
    """

    title = """
        <head>
            <title>Node Creator 4000</title>
        </head>
    """

    dont_resubmit = """
        <script>
        if ( window.history.replaceState ) {
            window.history.replaceState( null, null, window.location.href );
        }
        </script>
    """

    submit_form = """
        <div>
            <form action="/" method="post" id="vm_create_form">
                <label for="url">Paste the discovery iso URL into this box</label>
                <br />
                <textarea id="url" name="url" rows="4" cols="150"></textarea>
                <br />
                <label for="numofnodes">Number of nodes you want to create</label>
                <br />
                <input type="text" id="numofnodes" name="numofnodes" value="3">
                <br />
                <label for="nodes-prefix">Optional prefix (not visible to user anywhere, just helps to manage the resources)</label>
                <br />
                <input type="text" id="nodes-prefix" name="node-prefix" value="">

            </form>
            <button type="submit" form="vm_create_form" value="Submit">Submit</button>
        <div>
        <br />
    """

    logout_button = """
        <br/ ><a href="/logout">logout</a>
    """

    vm_create_screen = title + submit_form + get_running_vms() + logout_button

    status = get_status()
    in_progress_message = "Host creation in progress. Please wait until the process finished before submitting a next request. Current status: " + status

    if status != "":
        vm_create_screen = in_progress_message + refresher + logout_button
    if request.method == 'POST':
        if get_status() != "":
            return in_progress_message + logout_button + dont_resubmit + refresher

        num_of_nodes = request.form['numofnodes'].strip()
        if num_of_nodes == "":
            num_of_nodes = "3"
        elif not num_of_nodes.isnumeric():
            return "The number of nodes have to be a number" + dont_resubmit + title

        url = request.form['url']
        url = url.strip()
        if url.startswith('wget'):
            url = re.sub(r"wget -O .*\.iso '", '', url)[:-1]

        if url == "":
            return "The URL can not be empty" + dont_resubmit + title
        if not validators.url(url):
            return "The provided URL is not an actual URL" + dont_resubmit + title

        prefix = request.form['node-prefix']
        if prefix != "":
            prefix = prefix.replace(" ", "")

        if prefix == "":
            prefix = "unset"

        start_vms_on_background(url, num_of_nodes, prefix)
        return "<div>The host creation has been submitted. The hosts should start showing up in the wizard in few minutes</div><br /> Current status: " + get_status() + dont_resubmit + refresher
    else:
        return vm_create_screen

@app.route('/manage', methods=['GET', 'POST'])
@auth.login_required
def manage_vms():
    def delete_vms_on_background(vms):
        subprocess.run(['./delete_vms.sh'] + vms)

    def get_running_vms():
        form_header = """
            <form action="/manage" method="post" id="vm_delete_form">
        """
        form_footer = """
            <br /> <button type="submit" form="vm_delete_form" value="Submit">Delete selected VMs</button>
        </form>
        """

        vm_list = subprocess.check_output(['./get_running_vms.sh']).decode("utf-8").strip().split()
        vm_checkboxes = [f'<input type="checkbox" id="{vm}" name="vmname" value="{vm}"><label for="{vm}">{vm}</label>'  for vm in vm_list]
        vms_joined = "<br />".join(vm_checkboxes)

        return form_header + vms_joined + form_footer

    back_button = """
        <br/ ><a href="/">Back</a> to vm creation form
    """

    if request.method == 'POST':
        vm_list = request.form.getlist('vmname')
        if (len(vm_list) > 0):
            delete_vms_on_background(vm_list)

    return get_running_vms() + back_button
