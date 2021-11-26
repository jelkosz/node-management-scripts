from flask import Flask
from flask import request
import subprocess
import re
import validators

app = Flask(__name__)

# Dear poor person looking at this code. I apologise.
# --Tomas

@app.route('/', methods=['GET', 'POST'])
def create_vms():
    def get_status():
        wget = subprocess.check_output(['/root/webapp/get_running_process_count.py', 'wget']).decode("utf-8").strip()
        virt_install = subprocess.check_output(['/root/webapp/get_running_process_count.py', 'virt-install']).decode("utf-8").strip()

        if wget != "2":
            return "<div>An image is being downloaded</div>"
        elif virt_install != "2":
            return "<div>The VM(s) are being created</div> <br/>"
        return ""

    def start_vms_on_background(url, num_of_nodes):
        clear_url = url.strip()
        if clear_url.startswith('wget'):
            clear_url = re.sub(r"wget -O .*\.iso '", '', clear_url)[:-1]
        clear_num_of_nodes = num_of_nodes.strip()
        if not clear_num_of_nodes:
            # default
            clear_num_of_nodes = 3

        subprocess.Popen(['./runner.sh', clear_url, clear_num_of_nodes])

    dont_resubmit = """
        <script>
        if ( window.history.replaceState ) {
            window.history.replaceState( null, null, window.location.href );
        }
        </script>
    """

    submit_form = """
        <div>
            <form action="/" method="post" id="form1">
                <label for="url">Paste the discovery iso URL into this box</label>
                <br />
                <textarea id="url" name="url" rows="4" cols="150"></textarea>
                <br />
                <label for="num of nodes">Number of nodes you want to create</label>
                <br />
                <input type="text" id="numofnodes" name="numofnodes" value="3">
            </form>
            <button type="submit" form="form1" value="Submit">Submit</button>
        <div>
    """
    div = submit_form
    status = get_status()
    in_progress_message = "Host creation in progress. Please wait until the process finished before submitting a next request. Current status: " + status

    if status != "":
        div = in_progress_message
    if request.method == 'POST':
        if get_status() != "":
            return in_progress_message + dont_resubmit

        num_of_nodes = request.form['numofnodes']
        if num_of_nodes == "":
            num_of_nodes = 3
        elif not num_of_nodes.isnumeric():
            return "The number of nodes have to be a number" + dont_resubmit

        url = request.form['url']
        if not validators.url(url):
            return "The provided URL is not an actual URL" + dont_resubmit
        if url == "":
            return "The URL can not be empty" + dont_resubmit

        start_vms_on_background(request.form['url'], request.form['numofnodes'])
        return "<div>The host creation has been submitted. The hosts should start showing up in the wizard in few minutes</div><br /> Current status: " + get_status() + dont_resubmit
    else:
        return div

