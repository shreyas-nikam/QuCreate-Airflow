# Standard Library Imports
import os
import logging
import base64
from datetime import datetime, timedelta
from pathlib import Path
import shutil

# Third-Party Imports
from google import genai
from dotenv import load_dotenv
from bson import ObjectId

# Airflow Imports
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.ssh.operators.ssh import SSHOperator
from airflow.providers.ssh.hooks.ssh import SSHHook
from airflow.operators.bash import BashOperator


# Local Application Imports
from utils.prompt_handler import PromptHandler
from utils.mongodb_client import AtlasClient
from utils.s3_file_manager import S3FileManager
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
    """
    Fetch lab details from MongoDB and update the port configuration.
    This function is designed to be used as an Airflow task. It performs the following steps:
    1. Extracts the 'entry_id' from the Airflow DAG run configuration (provided via kwargs).
    2. Logs the extracted 'entry_id' for debugging purposes.
    3. Reads the current port from 'ports.txt', increments it, and logs the port.
    4. Uses a custom MongoDB client (AtlasClient) to find the MongoDB entry associated with the given 'entry_id'.
    5. Validates that the MongoDB entry exists and contains a 'lab_id'.
    6. Returns the 'lab_id' along with the incremented port.
    Parameters:
        **kwargs: dict
            Keyword arguments containing:
                - 'dag_run': Object with a 'conf' attribute that is a dictionary.
                  The 'conf' dictionary must include the key 'entry_id' which is used to query MongoDB.
    Returns:
        tuple:
            A tuple containing:
                - lab_id (str): The lab identifier obtained from the MongoDB entry.
                - port (int): The incremented port number read from 'ports.txt'.
    Raises:
        ValueError:
            If the entry is not found in MongoDB or if the found entry does not contain a 'lab_id'.
    """
    # Extract the 'entry_id' from the Airflow DAG run configuration
    entry_id = kwargs["dag_run"].conf.get("entry_id")
    logging.info(entry_id)

    # Log a message for debugging purposes, indicating the start of detail fetching
    logging.info(f"Fetching details for entry with ID: {entry_id}")
    
    # Open the file 'ports.txt' to read the current port number
    with open("ports.txt", "r") as f:
        port = int(f.readline().strip())
    # Increment the port number by one for the new lab instance
    port += 1
    
    # Create an instance of the custom MongoDB client to query the database
    mongodb_client = AtlasClient()
    # Query the 'in_lab_generation_queue' collection for the document with the specific entry_id
    entry = mongodb_client.find("in_lab_generation_queue", filter={"_id": ObjectId(entry_id)})
    
    # Raise an error if no document is found with the provided entry_id
    if not entry:
        raise ValueError("Entry not found in MongoDB")

    # Extract the first result from the query result list
    entry = entry[0]
    # Retrieve the associated lab_id from the MongoDB document
    lab_id = entry.get("lab_id")
    
    # Raise an error if lab_id is not present in the document
    if not lab_id:
        raise ValueError("No lab_id in the MongoDB entry")

    # Log the fetched lab_id for debugging purposes
    logging.info(f"Found lab_id: {lab_id}")
    
    # Return the lab_id and the incremented port number for further processing in the DAG
    return lab_id, port

def get_streamlit_code(lab_id, **kwargs):
    """
    Generates Streamlit application code based on lab technical specifications and raw resources.
    This function retrieves a lab design from MongoDB using its ID, then constructs a prompt 
    for generating Streamlit code. It downloads any associated raw resource files from S3, uploads 
    them to the Gemini API, and appends their references to the prompt content. Finally, it generates 
    the Streamlit code by invoking the Gemini API, performs minor formatting adjustments on the 
    response, cleans up downloaded files, and returns the final code.

    Parameters:
        lab_id (str): The unique identifier of the lab design document in MongoDB.
        **kwargs: Additional keyword arguments (currently not used).

    Returns:
        str: A string containing the generated Streamlit code.

    Raises:
        ValueError: If no lab design matching the provided lab_id is found in MongoDB.

    Notes:
        - The function relies on several external components:
            * PromptHandler for retrieving and formatting prompts.
            * AtlasClient for querying the MongoDB database.
            * S3FileManager for downloading files from AWS S3.
            * genai.Client for interacting with the Gemini API.
        - The function creates a temporary download directory to store raw resource files 
            and deletes it after use.
        - The code performs logging of the prompt and API responses for debugging purposes.
    """
    # Get prompt template for Streamlit app generation
    prompt = PromptHandler().get_prompt("STREAMLIT_APP_PROMPT")
    
    # Initialize MongoDB and S3 clients
    atlas_client = AtlasClient()
    s3_file_manager = S3FileManager()

    # Fetch lab design from MongoDB
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})
    if not lab:
        raise ValueError("Lab not found in MongoDB")
    lab = lab[0]
    
    # Extract technical specifications from lab design
    technical_specifications = lab.get("technical_specifications")

    # Format prompt with technical specifications
    streamlit_code_prompt = prompt.format(TECH_SPEC=technical_specifications)
    logging.info("Updated prompt for generating streamlit code:", streamlit_code_prompt)
    logging.info("================================================================")

    # Initialize Gemini API client
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    # List to store uploaded file references
    uploaded_files = []

    # Create temporary directory for downloading files
    download_path = f"downloads/lab_design/{lab_id}"
    Path(download_path).mkdir(parents=True, exist_ok=True)

    # Process raw resources from lab design
    raw_resources = lab.get("raw_resources", [])
    for resource in raw_resources:
        resource_link = resource.get("resource_link")
        # Extract S3 key from resource link
        key = f"qu-lab-design/{resource_link.split('qu-lab-design/')[1]}"
        download_file_path = f"{download_path}/{resource_link.split('/')[-1]}"
        
        # Download file from S3
        s3_file_manager.download_file(key, download_file_path)
        
        # Upload file to Gemini API
        uploaded_files.append(client.files.upload(file=download_file_path))

    # Generate Streamlit code using Gemini API
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL"),
        contents=[streamlit_code_prompt]+uploaded_files,
    ).text

    logging.info("Response from Gemini API:", response)

    # Clean up code response by removing markdown code blocks
    if "```python" in response:
        response = response[response.index("```python")+9:response.rindex("```")]
    if not response.startswith("import") and "import" in response:
        response = response[response.index("import"):]

    # Clean up downloaded files
    shutil.rmtree(download_path)

    return response


def get_claat_codelab(lab_id, streamlit_code, **kwargs):
    prompt = PromptHandler().get_prompt("GET_CODELAB_PROMPT")
    codelab_prompt = prompt.format(STREAMLIT_CODE=streamlit_code)
    logging.info("Updated prompt for generating codelab:", codelab_prompt)
    logging.info("================================================================")

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL"),
        contents=codelab_prompt,
    ).text

    logging.info("Response from Gemini API:", response)

    response = "id: "+lab_id+"\n\n"+response.replace("---", "")

    return response


def get_requirements_file(streamlit_code, **kwargs):
    """
    Generate a requirements.txt file content based on provided Streamlit code.

    This function takes a Streamlit application code as input, sends it to Google's Gemini AI
    model with a specialized prompt to analyze dependencies, and returns the required packages
    as a string suitable for a requirements.txt file.

    Args:
        streamlit_code (str): The Streamlit application code to analyze for dependencies
        **kwargs: Additional keyword arguments (currently unused)

    Returns:
        str: A string containing the required packages and their versions, formatted for
             requirements.txt. If the response contains markdown code blocks (```), only the
             content between the first and last blocks is returned.

    Raises:
        Potential exceptions from Gemini API calls are not explicitly handled.

    Example:
        requirements = get_requirements_file(streamlit_code)
        # Returns: 'streamlit==1.2.0\npandas==1.3.0\n...'
    """
    # Get the requirements file prompt template from PromptHandler
    prompt = PromptHandler().get_prompt("REQUIREMENTS_FILE_PROMPT")

    # Format the prompt by inserting the Streamlit code
    requirements_prompt = prompt.format(STREAMLIT_APP=streamlit_code)
    # Log the formatted prompt for debugging
    logging.info("Updated Prompt for requirements file:", requirements_prompt)
    logging.info("================================================================")

    # Initialize the Gemini AI client with API key
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    # Generate requirements using Gemini AI model
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL"),
        contents=requirements_prompt,
    ).text

    # Log the raw response from Gemini API
    logging.info("Response from Gemini API:", response)

    # Clean up the response by removing markdown code blocks if present
    if "```" in response:
        response = response[response.index("```")+3:response.rindex("```")]
    return response

def get_readme_file(lab_id, streamlit_code, **kwargs):
    """
    Generate a README.md file content for a lab project using AI.

    Args:
        lab_id (str): Unique identifier for the lab project
        streamlit_code (str): The Streamlit application code to reference in README
        **kwargs: Additional keyword arguments (unused)

    Returns:
        str: Generated README content in markdown format

    The function:
    1. Gets a README template prompt from PromptHandler
    2. Formats the prompt with lab_id and Streamlit code
    3. Uses Gemini AI to generate appropriate README content
    4. Returns the generated markdown text
    """
    # Get the README template prompt from PromptHandler
    prompt = PromptHandler().get_prompt("README_FILE_PROMPT")

    # Format the prompt with the lab_id and Streamlit code
    readme_prompt = prompt.format(LAB_ID=lab_id)
    prompt = prompt.format(STREAMLIT_CODE=streamlit_code)

    # Log the formatted prompt for debugging
    logging.info("Updated prompt for README file:", readme_prompt)
    logging.info("================================================================")

    # Initialize Gemini AI client with API key
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    # Generate README content using Gemini AI
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL"),
        contents=readme_prompt,
    ).text

    # Log the response from Gemini API
    logging.info("Response from Gemini API:", response)

    return response

def upload_files_to_github(lab_id, port, streamlit_code, requirements, readme, **kwargs):
    """
    Upload multiple files to a GitHub repository for a lab project.

    Args:
        lab_id (str): Unique identifier for the lab
        port (int): Port number for the lab service
        streamlit_code (str): Content of the Streamlit application
        requirements (str): Content of requirements.txt file
        readme (str): Content of README.md file
        **kwargs: Additional keyword arguments

    Returns:
        bool: True if all files are uploaded/updated successfully

    The function uploads or updates the following files:
    - app.py (Streamlit application)
    - requirements.txt (Python dependencies)
    - README.md (Project documentation)
    - Dockerfile (Container configuration)
    - docker-compose.yml (Service orchestration)
    - .streamlit/config.toml (Streamlit configuration)
    """
    # Define list of files to be uploaded with their respective contents and commit messages
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
        "file_path": "README.md",
        "content": readme,
        "commit_message": "Add README file"
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

    # Attempt to upload each file, if file exists then update it
    for file in files:
        if upload_file_to_github(lab_id, file["file_path"], file["content"], file["commit_message"]):
            logging.info(f"File {file['file_path']} uploaded successfully!")
        else:
            update_file_in_github(lab_id, file["file_path"], file["content"], file["commit_message"])
            logging.info(f"File {file['file_path']} updated successfully!")
    return True

def send_notification(lab_id, port):
    """
    Send notifications to users associated with a lab.

    Args:
        lab_id (str): Unique identifier for the lab
        port (int): Port number for the lab service
    """
    # Fetch lab details from MongoDB
    atlas_client = AtlasClient()
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})[0]
    users = lab.get("users", [])
    
    # Create and send notifications to all users
    message = f"Your lab is ready for review."
    for user in users:
        notifications_object = {
            "username": user,
            "creation_date": datetime.now(),
            "type": "lab",
            "message": message,
            "read": False,
            "project_id": lab_id
        }
        atlas_client.insert("notifications", notifications_object)

def final_task(lab_id, port, **kwargs):
    """
    Perform final cleanup and updates after lab deployment.

    Args:
        lab_id (str): Unique identifier for the lab
        port (int): Port number for the lab service
        **kwargs: Additional keyword arguments
    """
    # Update ports.txt with the latest port number
    with open("ports.txt", "w") as f:
        f.write(str(port))
    
    # Update lab status and URLs in MongoDB
    mongodb_client = AtlasClient()
    lab_url = f"https://qucreate.qusandbox.com/{lab_id}"
    repo_url = f"https://github.com/{GITHUB_USERNAME}/{lab_id}"
    documentation_url = f"https://qucreate.qusandbox.com/documentation/{lab_id}/"
    mongodb_client.update("lab_design", 
                            filter={"_id": ObjectId(lab_id)}, 
                            update={"$set": {"status": "Project Review", 
                                        "lab_url": lab_url, 
                                        "repo_url": repo_url,
                                        "documentation_url": documentation_url}})
    logging.info(f"Updated lab {lab_id} with review status and URLs")
    
    # Send notification to users
    send_notification(lab_id, port)

    # Remove lab from generation queue
    mongodb_client.delete("in_lab_generation_queue", filter={"lab_id": lab_id})
    logging.info("Lab deployment complete!")

def failure_callback(context):
    """
    Handle failures in the DAG execution.

    Args:
        context (dict): Airflow context containing information about the failed task

    This function:
    1. Logs the error
    2. Updates MongoDB status to 'failed'
    3. Sends failure notifications to users
    4. Removes the failed entry from the generation queue
    """
    # Extract entry ID from the context
    dag_run = context.get("dag_run")
    entry_id = dag_run.conf.get("entry_id")
    logging.error(f"DAG failed for entry ID: {entry_id}")

    mongodb_client = AtlasClient()
    entry = mongodb_client.find("in_lab_generation_queue", filter={"_id": ObjectId(entry_id)})

    if entry:
        # Extract lab information
        entry = entry[0]
        lab_id = entry.get("lab_id")
        if not lab_id:
            logging.error("No lab_id in the MongoDB entry")
            return
        
        # Update lab status to failed
        mongodb_client.update("lab_design", 
                            filter={"_id": ObjectId(lab_id)}, 
                            update={"$set": {"status": "Lab Generation Failed"}})
        logging.info(f"Updated lab {lab_id} with failed status")

        # Fetch lab details for notification
        lab = mongodb_client.find("lab_design", filter={"_id": ObjectId(lab_id)})[0]
        
        # Send failure notifications to users
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

        # Remove failed entry from queue
        mongodb_client.delete("in_lab_generation_queue", filter={"_id": ObjectId(entry_id)})
        logging.info(f"Deleted entry {entry_id} from MongoDB after failure.")


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
    "on_failure_callback": failure_callback,
}


def build_command(command_template, inputs, **kwargs):
    """
    Format a multi-line shell command by injecting the inputs dict.
    Example: command_template='echo "{MSG}"', inputs={'MSG': 'Hello'}
    """
    command = command_template.format(**inputs)
    logging.info(f"Built command: {command}")
    return command

# DAG definition
with DAG(
    dag_id="lab_generation_dag",
    default_args=default_args,
    description="Fetch lab_id from MongoDB and deploy locally",
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

    get_claat_codelab_task = PythonOperator(
        task_id="get_claat_codelab",
        python_callable=get_claat_codelab,
        provide_context=True,
        op_args=["{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
                    "{{ ti.xcom_pull(task_ids='get_streamlit_code') }}"],
    )
    
    get_requirements_file_task = PythonOperator(
        task_id="get_requirements_file",
        python_callable=get_requirements_file,
        provide_context=True,
        op_args=["{{ ti.xcom_pull(task_ids='get_streamlit_code') }}"],
    )

    get_readme_file_task = PythonOperator(
        task_id="get_readme_file",
        python_callable=get_readme_file,
        provide_context=True,
        op_args=["{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}", 
                 "{{ ti.xcom_pull(task_ids='get_streamlit_code') }}"],
    )

    upload_files_to_github_task = PythonOperator(
        task_id="upload_files_to_github",
        python_callable=upload_files_to_github,
        provide_context=True,
        op_args=["{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}", 
                 "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[1] }}", 
                 "{{ ti.xcom_pull(task_ids='get_streamlit_code') }}", 
                 "{{ ti.xcom_pull(task_ids='get_requirements_file') }}",
                 "{{ ti.xcom_pull(task_ids='get_readme_file') }}"
                 ],
    )


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
        python_callable=build_command,
        op_args=[
            pull_remote_command, 
            {
                "LAB_ID": "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
                "GITHUB_USERNAME": GITHUB_USERNAME
            }
        ],
        provide_context=True
    )


    pull_repo_remote = BashOperator(
        task_id="pull_repo_remote",
        bash_command="{{ task_instance.xcom_pull(task_ids='build_pull_repo_command') }}",
        do_xcom_push=True,
    )

    
    docker_compose_command = """
LAB_ID="{LAB_ID}"
cd /home/ubuntu/QuLabs/$LAB_ID
sudo docker compose build
"""

    build_docker_compose_command = PythonOperator(
        task_id="build_docker_compose_command",
        python_callable=build_command,
        op_args=[docker_compose_command, {
            "LAB_ID": "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
        }],
        provide_context=True
    )


    # 3) Docker-compose build
    docker_compose_build = BashOperator(
        task_id="docker_compose_build",
        bash_command="{{ task_instance.xcom_pull(task_ids='build_docker_compose_command') }}",
        do_xcom_push=True,
    )


    docker_compose_up_command = """
LAB_ID="{LAB_ID}"
cd /home/ubuntu/QuLabs/$LAB_ID
sudo docker compose up -d
"""

    build_docker_compose_up_command = PythonOperator(
        task_id="build_docker_compose_up_command",
        python_callable=build_command,
        op_args=[docker_compose_up_command, {
            "LAB_ID": "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
        }],
        provide_context=True
    )


    # 4) Docker-compose up
    docker_compose_up = BashOperator(
        task_id="docker_compose_up",
        bash_command="{{ task_instance.xcom_pull(task_ids='build_docker_compose_up_command') }}",
        do_xcom_push=True,
    )

    update_nginx_snippet_command = """
LAB_ID="{LAB_ID}"
LAB_PORT={PORT}

echo "Updating Nginx snippet for lab: $LAB_ID on port $LAB_PORT"
/usr/local/bin/add_lab.sh $LAB_ID $LAB_PORT
"""

    build_update_nginx_snippet_command = PythonOperator(
        task_id="build_update_nginx_snippet_command",
        python_callable=build_command,
        op_args=[update_nginx_snippet_command, {
            "LAB_ID": "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
            "PORT": "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[1] }}",
        }],
        provide_context=True
    )


    # 5) Update Nginx snippet
    #    We assume lab_id uses a standard port assignment or we store the port in the DB too.
    #    Example: all labs run on 8501 for single-lab approach, or you store a dynamic port in Mongo.
    update_nginx_snippet = BashOperator(
        task_id="update_nginx_snippet",
        bash_command="{{ task_instance.xcom_pull(task_ids='build_update_nginx_snippet_command') }}",
        do_xcom_push=True,
    )


    # 6) Claat command and documentation
    claat_command = """
export LAB_ID="{LAB_ID}"
nano /home/ubuntu/QuLabs/documentation/$LAB_ID/documentation.md
echo {CLAAT_DOCUMENTATION} > /home/ubuntu/QuLabs/documentation/$LAB_ID/documentation.md
claat export /home/ubuntu/QuLabs/documentation/$LAB_ID/documentation.md
sudo mkdir /var/www/codelabs/$LAB_ID
sudo cp -r /home/ubuntu/QuLabs/documentation/$LAB_ID/$LAB_ID/. /var/www/codelabs/$LAB_ID
"""

    build_claat_command = PythonOperator(
        task_id="build_claat_command",
        python_callable=build_command,
        op_args=[claat_command, {
            "LAB_ID": "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
            "CLAAT_DOCUMENTATION": "{{ ti.xcom_pull(task_ids='get_claat_codelab') }}"
        }],
        provide_context=True
    )

    claat_command_step = BashOperator(
        task_id="claat_command",
        bash_command="{{ task_instance.xcom_pull(task_ids='build_claat_command') }}",
        do_xcom_push=True,
    )

    end = PythonOperator(
        task_id="end",
        python_callable=final_task,
        provide_context=True,
        op_args=["{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}", 
                 "{{ ti.xcom_pull(task_ids='fetch_details_from_mongo')[1] }}"],
    )


    fetch_details_from_mongo_step >> \
    get_streamlit_code_task >> \
    get_claat_codelab_task >> \
    get_requirements_file_task >> \
    get_readme_file_task >> \
    upload_files_to_github_task >> \
    build_pull_repo_command >> \
    pull_repo_remote >> \
    build_docker_compose_command >> \
    docker_compose_build >> \
    build_docker_compose_up_command >> \
    docker_compose_up >> \
    build_update_nginx_snippet_command >> \
    update_nginx_snippet >> \
    build_claat_command >> \
    claat_command_step >> \
    end