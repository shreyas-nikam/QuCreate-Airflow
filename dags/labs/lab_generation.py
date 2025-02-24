# Standard Library Imports
import os
import logging
import base64
from datetime import datetime, timedelta

# Third-Party Imports
from google import genai
from dotenv import load_dotenv
from bson import ObjectId

# Airflow Imports
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.ssh.operators.ssh import SSHOperator
from airflow.providers.ssh.hooks.ssh import SSHHook

# Local Application Imports
from utils.prompt_handler import PromptHandler
from utils.mongodb_client import AtlasClient
from labs.github_helpers import upload_file_to_github, update_file_in_github

load_dotenv()
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")


docker_compose_file="""version: "3.8"

services:
  {LAB_ID}_service:
    build: .
    container_name: {LAB_ID}_container
    # Adjust your desired external port mapping here. For example:
    # "8502:8501" means the app is internally on 8501, but externally accessible on 8502.
    ports:
      - "{PORT}:8501"
    environment:
      - PORT=8501  # This must match the internal port used by Streamlit
    restart: always
"""

docker_file="""# Use Python base image
FROM python:3.8-slim

# Set working directory in the container
WORKDIR /app

# Copy requirements (adjust file name if needed)
COPY requirements.txt /app/

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . /app

# Set the port number via build-time or run-time environment
# We'll default it to 8501, but you can override later.
ENV PORT=8501

# Expose the port so Docker maps it
EXPOSE $PORT

# Run Streamlit
CMD ["bash", "-c", "streamlit run app.py --server.port=$PORT --server.headless=true"]
"""

streamlit_conf_file="""[server]
port = {PORT}
baseUrlPath = "{LAB_ID}"
enableCORS = false
enableXsrfProtection = false
"""

def fetch_details_from_mongo_task(**kwargs):
    entry_id = kwargs["dag_run"].conf.get("entry_id")
    logging.info(entry_id)
    
    logging.info(f"Fetching details for entry with ID: {entry_id}")
    with open("ports.txt", "r") as f:
        port = int(f.readline().strip())
    port+=1
    mongodb_client = AtlasClient()  # Your own MongoDB client
    entry = mongodb_client.find("in_lab_generation_queue", filter={"_id": ObjectId(entry_id)})
    if not entry:
        raise ValueError("Entry not found in MongoDB")

    entry = entry[0]
    lab_id = entry.get("lab_id")
    if not lab_id:
        raise ValueError("No lab_id in the MongoDB entry")

    logging.info(f"Found lab_id: {lab_id}")
    return lab_id, port


def get_streamlit_code(lab_id, **kwargs):
    prompt = PromptHandler().get_prompt("STREAMLIT_APP_PROMPT")
    atlas_client = AtlasClient()
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})
    if not lab:
        raise ValueError("Lab not found in MongoDB")
    lab = lab[0]
    technical_specifications = lab.get("technical_specifications")

    streamlit_code_prompt = prompt.format(TECH_SPEC=technical_specifications)
    logging.info("Updated prompt for generating streamlit code:", streamlit_code_prompt)
    logging.info("================================================================")

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL"),
        contents=streamlit_code_prompt,
    ).text

    logging.info("Response from Gemini API:", response)

    if "```python" in response:
        response = response[response.index("```python")+9:response.rindex("```")]
    if not response.startswith("import") and "import" in response:
        response = response[response.index("import"):]

    return response

def get_requirements_file(streamlit_code, **kwargs):
    # get prompt, fill it with streamlit code, get requirements, clean it, return response
    prompt = PromptHandler().get_prompt("REQUIREMENTS_FILE_PROMPT")

    requirements_prompt = prompt.format(STREAMLIT_APP=streamlit_code)
    logging.info("Updated Prompt for requirements file:", requirements_prompt)
    logging.info("================================================================")

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL"),
        contents=requirements_prompt,
    ).text

    logging.info("Response from Gemini API:", response)

    if "```" in response:
        response = response[response.index("```")+3:response.rindex("```")]
    return response
    

def upload_files_to_github(lab_id, port, streamlit_code, requirements, **kwargs):
    # upload the streamlit code, requirements file, Dockerfile, docker-compose file, Github actions file, streamlit conf file to github repo
    # upload_file_to_github(lab_id, "app.py", streamlit_code, "Add Streamlit app")
    # upload_file_to_github(lab_id, "requirements.txt", requirements, "Add requirements.txt")
    files = [{
        "file_path": "app.py", 
        "content": streamlit_code,
        "commit_message": "Add Streamlit app"
    },
    {
        "file_path": "requirements.txt",
        "content": requirements,
        "commit_message": "Add requirements.txt"
    },
    {
        "file_path": "Dockerfile",
        "content": docker_file,
        "commit_message": "Add Dockerfile"
    },
    {
        "file_path": "docker-compose.yml",
        "content": docker_compose_file.format(LAB_ID=lab_id, PORT=port),
        "commit_message": "Add docker-compose file"
    },
    {
        "file_path": ".streamlit/config.toml",
        "content": streamlit_conf_file.format(LAB_ID=lab_id, PORT=port),
        "commit_message": "Add Streamlit conf file"
    }
    ]
    for file in files:
        if upload_file_to_github(lab_id, file["file_path"], file["content"], file["commit_message"]):
            logging.info(f"File {file['file_path']} uploaded successfully!")
        else:
            update_file_in_github(lab_id, file["file_path"], file["content"], file["commit_message"])
            logging.info(f"File {file['file_path']} updated successfully!")
    return True

def send_notification(lab_id, port):
    atlas_client = AtlasClient()
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})[0]
    users = lab.get("users", [])
    message = f"Your lab is ready for review."
    for user in users:
        notifications_object = {
            "username": user,
            "creation_date": datetime.now(),
            "type": "course_module",
            "message": message,
            "read": False,
            "project_id": lab_id
        }
        atlas_client.insert("notifications", notifications_object)

def final_task(lab_id, port, **kwargs):
    # update the port in ports.txt file
    with open("ports.txt", "w") as f:
        f.write(str(port))
    
    # update the lab status in mongodb
    mongodb_client = AtlasClient()
    
    lab_url = f"https://qucreate.qusandbox.com/{lab_id}"
    repo_url = f"https://github.com/{GITHUB_USERNAME}/{lab_id}"
    mongodb_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={"$set": {"status": "Project Review", "lab_url": lab_url, "repo_url": repo_url}})
    
    # send notification to user
    send_notification(lab_id, port)

    # delete entry from mongo
    mongodb_client.delete("in_lab_generation_queue", filter={"lab_id": lab_id})

    logging.info("Lab deployment complete!")



def failure_callback(context):
    """
    Function to handle failures in the DAG.
    1. Logs the error.
    2. Updates MongoDB status to 'failed'.
    3. Sends a failure notification.
    4. Deletes the entry from MongoDB.
    """
    dag_run = context.get("dag_run")
    entry_id = dag_run.conf.get("entry_id")

    logging.error(f"DAG failed for entry ID: {entry_id}")

    mongodb_client = AtlasClient()
    entry = mongodb_client.find("in_lab_generation_queue", filter={"_id": ObjectId(entry_id)})

    if entry:

        entry = entry[0]
        lab_id = entry.get("lab_id")
        if not lab_id:
            logging.error("No lab_id in the MongoDB entry")
            return
        
        # Update MongoDB status to 'failed'
        mongodb_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={"$set": {"status": "Failed"}})
        logging.info(f"Updated lab {lab_id} with failed status")

        lab = mongodb_client.find("lab_design", filter={"_id": ObjectId(lab_id)})[0]
        
        # Send failure notification
        message = f"Processing of the lab for {lab['lab_name']} failed. Please contact the administrator."
        users = lab.get("users", [])
        for user in users:
            notification = {
                "username": user,
                "creation_date": datetime.now(),
                "type": "course_module",
                "message": message,
                "read": False,
                "project_id": lab_id
            }
            mongodb_client.insert("notifications", notification)

        # Delete the entry from MongoDB
        mongodb_client.delete("in_lab_generation_queue", filter={"_id": ObjectId(entry_id)})
        logging.info(f"Deleted entry {entry_id} from MongoDB after failure.")


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
    "on_failure_callback": failure_callback,
}

# Name of your Airflow SSH connection to EC2
SSH_CONN_ID = "ec2_ssh"

# DAG definition
with DAG(
    dag_id="lab_generation_dag",
    default_args=default_args,
    description="Fetch lab_id from MongoDB and deploy to EC2",
    start_date=datetime(2023, 1, 1),
    schedule_interval=None,  # Run on demand
    catchup=False,
) as dag:
    
    fetch_details_from_mongo_step = PythonOperator(
        task_id="fetch_details_from_mongo",
        python_callable=fetch_details_from_mongo_task,
        provide_context=True,
    )

    get_streamlit_code_task = PythonOperator(
        task_id="get_streamlit_code",
        python_callable=get_streamlit_code,
        provide_context=True,
        op_args=["{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}"],
    )

    get_requirements_file_task = PythonOperator(
        task_id="get_requirements_file",
        python_callable=get_requirements_file,
        provide_context=True,
        op_args=["{{ ti.xcom_pull(task_ids='get_streamlit_code') }}"],
    )

    upload_files_to_github_task = PythonOperator(
        task_id="upload_files_to_github",
        python_callable=upload_files_to_github,
        provide_context=True,
        op_args=["{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}", "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[1] }}", "{{ ti.xcom_pull(task_ids='get_streamlit_code') }}", "{{ ti.xcom_pull(task_ids='get_requirements_file') }}"],
    )

    
    def print_ssh_output(task_id, **kwargs):
        # Pull the output from the 'run_ssh_command' task
        task_instance = kwargs["ti"]
        ssh_output = task_instance.xcom_pull(task_ids=task_id)
        decoded_output = base64.b64decode(ssh_output).decode("utf-8")
        logging.info(f"SSH command returned:\n{decoded_output}")

    def fail_ssh_and_return(expected_message, task_id, **kwargs):
        # get the message, decode it and if it is not the same as the expected message, fail the task
        task_instance = kwargs["ti"]
        ssh_output = task_instance.xcom_pull(task_ids=task_id)
        decoded_output = base64.b64decode(ssh_output).decode("utf-8")
        
        if expected_message != decoded_output:
            # update in mongodb that there was an error. push notification to user.
        
            raise ValueError(f"Expected message not found in SSH output: {expected_message}") 
        
    def build_ssh_command(command, inputs, **kwargs):
        formatted_command = command.format(**inputs)
        logging.info(f"Built SSH command: {formatted_command}")
        return formatted_command
    

    pull_remote_command = """
LAB_ID="{LAB_ID}"
echo "Pulling repo for lab: $LAB_ID"

# Ensure folder exists
mkdir -p /home/ubuntu/QuLabs
cd /home/ubuntu/QuLabs

# If you haven't cloned the repo, do so. Otherwise, just pull updates.
# Adjust the GIT URL to your actual lab repository, or store it in Mongo if each lab has a unique repo.
if [ ! -d "$LAB_ID" ]; then
    git clone https://github.com/{GITHUB_USERNAME}/{LAB_ID}.git
else
    git pull origin main
fi
"""

    build_pull_repo_command = PythonOperator(
        task_id="build_pull_repo_command",
        python_callable=build_ssh_command,
        op_args=[pull_remote_command, {
            "LAB_ID": "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
            "GITHUB_USERNAME": GITHUB_USERNAME
        }],
        provide_context=True
    )


    pull_repo_remote = SSHOperator(
        task_id="pull_repo_remote",
        ssh_hook=SSHHook(ssh_conn_id=SSH_CONN_ID),
        get_pty=True,
        ssh_conn_id=SSH_CONN_ID,
        command="{{ task_instance.xcom_pull(task_ids='build_pull_repo_command') }}",
        do_xcom_push=True,
    )

    # print the output of the pull_repo_remote task
    print_pull_repo_output = PythonOperator(
        task_id="print_pull_repo_output",
        python_callable=print_ssh_output,
        op_args=["pull_repo_remote"],
        provide_context=True,
    )

    docker_compose_command = """
LAB_ID="{LAB_ID}"
cd /home/ubuntu/QuLabs/$LAB_ID
sudo docker compose build
"""

    build_docker_compose_command = PythonOperator(
        task_id="build_docker_compose_command",
        python_callable=build_ssh_command,
        op_args=[docker_compose_command, {
            "LAB_ID": "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
        }],
        provide_context=True
    )


    # 3) Docker-compose build
    docker_compose_build = SSHOperator(
        task_id="docker_compose_build",
        ssh_hook=SSHHook(ssh_conn_id=SSH_CONN_ID),
        get_pty=True,
        ssh_conn_id=SSH_CONN_ID,
        command="{{ task_instance.xcom_pull(task_ids='build_docker_compose_command') }}",
        do_xcom_push=True,
    )

    # print the output of the docker_compose_build task
    print_docker_compose_output = PythonOperator(
        task_id="print_docker_compose_output",
        python_callable=print_ssh_output,
        op_args=["docker_compose_build"],
        provide_context=True,
    )

    docker_compose_up_command = """
LAB_ID="{LAB_ID}"
cd /home/ubuntu/QuLabs/$LAB_ID
sudo docker compose up -d
"""

    build_docker_compose_up_command = PythonOperator(
        task_id="build_docker_compose_up_command",
        python_callable=build_ssh_command,
        op_args=[docker_compose_up_command, {
            "LAB_ID": "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
        }],
        provide_context=True
    )


    # 4) Docker-compose up
    docker_compose_up = SSHOperator(
        ssh_hook=SSHHook(ssh_conn_id=SSH_CONN_ID),
        task_id="docker_compose_up",
        get_pty=True,
        ssh_conn_id=SSH_CONN_ID,
        command="{{ task_instance.xcom_pull(task_ids='build_docker_compose_up_command') }}",
        do_xcom_push=True,
    )

    # print the output of the docker_compose_up task
    print_docker_compose_up_output = PythonOperator(
        task_id="print_docker_compose_up_output",
        python_callable=print_ssh_output,
        op_args=["docker_compose_up"],
        provide_context=True,
    )

    # conditional -> if the above command succeeds, update the port in ports.txt file to port+1

    update_nginx_snippet_command = """
LAB_ID="{LAB_ID}"
LAB_PORT={PORT}

echo "Updating Nginx snippet for lab: $LAB_ID on port $LAB_PORT"
/usr/local/bin/add_lab.sh $LAB_ID $LAB_PORT
"""

    build_update_nginx_snippet_command = PythonOperator(
        task_id="build_update_nginx_snippet_command",
        python_callable=build_ssh_command,
        op_args=[update_nginx_snippet_command, {
            "LAB_ID": "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
            "PORT": "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[1] }}",
        }],
        provide_context=True
    )


    # 5) Update Nginx snippet
    #    We assume lab_id uses a standard port assignment or we store the port in the DB too.
    #    Example: all labs run on 8501 for single-lab approach, or you store a dynamic port in Mongo.
    update_nginx_snippet = SSHOperator(
        ssh_hook=SSHHook(ssh_conn_id=SSH_CONN_ID),
        task_id="update_nginx_snippet",
        get_pty=True,
        ssh_conn_id=SSH_CONN_ID,
        command="{{ task_instance.xcom_pull(task_ids='build_update_nginx_snippet_command') }}",
        do_xcom_push=True,
    )

    # print the output of the update_nginx_snippet task
    print_nginx_snippet_output = PythonOperator(
        task_id="print_nginx_snippet_output",
        python_callable=print_ssh_output,
        op_args=["update_nginx_snippet"],
        provide_context=True,
    )

    end = PythonOperator(
        task_id="end",
        python_callable=final_task,
        provide_context=True,
        op_args=["{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}", "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[1] }}"],
    )


    fetch_details_from_mongo_step >> \
    get_streamlit_code_task >> \
    get_requirements_file_task >> \
    upload_files_to_github_task >> \
    build_pull_repo_command >> \
    pull_repo_remote >> \
    print_pull_repo_output >> \
    build_docker_compose_command >> \
    docker_compose_build >> \
    print_docker_compose_output >> \
    build_docker_compose_up_command >> \
    docker_compose_up >> \
    print_docker_compose_up_output >> \
    build_update_nginx_snippet_command >> \
    update_nginx_snippet >> \
    print_nginx_snippet_output >> \
    end