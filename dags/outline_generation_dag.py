import os
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from course.outline_generation import fetch_artifacts, upload_outline
from course.helper import parse_files, save_index, generate_outline
import asyncio
from utils.mongodb_client import AtlasClient
from bson.objectid import ObjectId
import logging
from airflow.operators.empty import EmptyOperator
from pathlib import Path
from datetime import datetime, timezone
from course.structure_generation import _get_course_and_module
from dotenv import load_dotenv
from utils.converter import _convert_object_ids_to_strings

load_dotenv()

def fetch_details_from_mongo(entry_id, **kwargs):
    logging.info(f"Fetching details for entry with ID: {entry_id}")
    entry_id = kwargs["dag_run"].conf.get("entry_id")
    mongodb_client = AtlasClient()
    entry = mongodb_client.find("in_outline_generation_queue", filter={
                                "_id": ObjectId(entry_id)})
    if not entry:
        return "Entry not found"

    entry = entry[0]
    course_id = entry.get("course_id")
    module_id = entry.get("module_id")
    instructions = entry.get("instructions")

    return course_id, module_id, instructions


def fetch_artifacts_task(course_id, module_id, **kwargs):
    logging.info("Fetching artifacts")
    logging.info(f"Course ID: {course_id}, Module ID: {module_id}")
    artifacts_path = fetch_artifacts(course_id, module_id)
    if not artifacts_path:
        logging.error("Error in fetching artifacts")
        raise Exception("Error in fetching artifacts")
    return artifacts_path


def parse_files_and_create_index_task(module_id, file_path, **kwargs):
    logging.info("Parsing files")
    download_path = f"output/{module_id}/files"
    vector_index = parse_files(module_id, file_path, download_path)
    logging.info("Files parsed")
    save_index(vector_index, Path("output") / module_id / "vector_index")


def generate_outline_task(course_id, module_id, instructions, **kwargs):
    logging.info("Generating outline")
    course, module = _get_course_and_module(course_id, module_id)
    module_name = module.get("module_name")
    module_description = module.get("module_description")
    instructions += f"\n\nModule Name: {module_name}\nModule Description: {module_description}"
    outline = asyncio.run(generate_outline(module_id, instructions))
    logging.info("Outline generated")
    return outline


def upload_outline_task(course_id, module_id, outline, **kwargs):
    logging.info("Uploading outline")
    upload_outline(course_id, module_id, outline)
    logging.info("Outline uploaded")
    return True


def delete_entry_from_mongodb_task(course_id, module_id, **kwargs):
    logging.info("Deleting entry from MongoDB")
    mongodb_client = AtlasClient()
    mongodb_client.delete("in_outline_generation_queue", filter={
                          "course_id": course_id, "module_id": module_id})
    logging.info("Entry deleted")
    return True


def add_notification_task(entry_id, course_id, module_id, **kwargs):

    course, module = _get_course_and_module(course_id, module_id)
    message = f"Module {module['module_name']} is ready for Outline Review."

    mongodb_client = AtlasClient()
    users = course.get("users", [])
    for user in users:
        notifications_object = {
            "username": user,
            "creation_date": datetime.now(timezone.utc).isoformat(),
            "type": "course_module",
            "message": message,
            "read": False,
            "module_id": module_id,
            "project_id": course_id
        }
        mongodb_client.insert("notifications", notifications_object)
        
        notifications_object["state"] = f"Done"
        url = f"{os.getenv('FASTAPI_BACKEND_URL')}/task-complete"  # Adjust for your FastAPI host/port
        response = requests.post(url, json=_convert_object_ids_to_strings(notifications_object))
        response.raise_for_status()
        
    return True



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
    entry = mongodb_client.find("in_outline_generation_queue", filter={"_id": ObjectId(entry_id)})

    if entry:

        course_id = entry[0].get("course_id")
        module_id = entry[0].get("module_id")
        course, module = _get_course_and_module(course_id, module_id)

        for index, module in enumerate(course['modules']):
            if module['module_id'] == ObjectId(module_id):
                course['modules'][index]['status'] = 'Outline Generation Failed'
                break

        mongodb_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": {"modules": course["modules"]}})
        logging.info(f"Updated course {course_id} with failed status for module {module_id}")
        # Send failure notification
        message = f"Processing of the outline for module {module['module_name']} failed. Please contact the administrator."
        users = course.get("users", [])
        for user in users:
            notification = {
            "username": user,
            "creation_date": datetime.now(timezone.utc).isoformat(),
                "type": "course_module",
                "message": message,
                "read": False,
                "module_id": module_id,
                "project_id": course_id
            }
            mongodb_client.insert("notifications", notification)
            
            notification["state"] = f"Failed"
            url = f"{os.getenv('FASTAPI_BACKEND_URL')}/task-complete"  # Adjust for your FastAPI host/port
            response = requests.post(url, json=_convert_object_ids_to_strings(notification))
            response.raise_for_status()

        # Delete the entry from MongoDB
        mongodb_client.delete("in_outline_generation_queue", filter={"_id": ObjectId(entry_id)})
        logging.info(f"Deleted entry {entry_id} from MongoDB after failure.")

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': days_ago(1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'on_failure_callback': failure_callback
}

with DAG(
    'outline_generation_dag',
    default_args=default_args,
    description='DAG for processing the outline generation queue entries',
    schedule_interval=None,  # Triggered externally
    catchup=False,
) as dag:

    start = EmptyOperator(task_id='start')

    # Fetch the entry from MongoDB
    fetch_entry = PythonOperator(
        task_id='fetch_entry_from_mongo',
        python_callable=fetch_details_from_mongo,
        # Pass entry_id from the dag run
        op_args=["{{ dag_run.conf['entry_id'] }}"],
        provide_context=True
    )

    # Fetch the artifacts
    fetch_artifacts_step = PythonOperator(
        task_id='fetch_artifacts',
        python_callable=fetch_artifacts_task,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}"],
        provide_context=True
    )

    # Parse the files and create index
    parse_files_and_create_index_step = PythonOperator(
        task_id='parse_files_and_create_index',
        python_callable=parse_files_and_create_index_task,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_artifacts') }}"],
        provide_context=True
    )

    # Generate the outline
    generate_outline_step = PythonOperator(
        task_id='generate_outline',
        python_callable=generate_outline_task,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[0] }}",
                    "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}",
                    "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[2] }}"],
        provide_context=True
    )

    # Upload the outline
    upload_outline_step = PythonOperator(
        task_id='upload_outline',
        python_callable=upload_outline_task,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}", "{{ task_instance.xcom_pull(task_ids='generate_outline') }}"],
        provide_context=True
    )

    # Delete the entry from MongoDB
    delete_entry_from_mongodb_step = PythonOperator(
        task_id='delete_entry_from_mongodb',
        python_callable=delete_entry_from_mongodb_task,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}"],
        provide_context=True
    )

    add_notification_step = PythonOperator(
        task_id='add_notification',
        python_callable=add_notification_task,
        op_args=["{{ dag_run.conf['entry_id'] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}"],
        provide_context=True
    )

    end = EmptyOperator(task_id='end')

    start >> fetch_entry >> fetch_artifacts_step >> parse_files_and_create_index_step >> generate_outline_step >> upload_outline_step >> delete_entry_from_mongodb_step >> add_notification_step >> end
