import logging
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.utils.dates import days_ago
from airflow.operators.empty import EmptyOperator
from course.publishing import handle_update_course, handle_create_course
from utils.mongodb_client import AtlasClient
from bson.objectid import ObjectId
from airflow.utils.edgemodifier import Label
from airflow.utils.trigger_rule import TriggerRule
from datetime import datetime, timezone
from course.structure_generation import _get_course_and_module
import os
import requests
from dotenv import load_dotenv
from utils.converter import _convert_object_ids_to_strings

load_dotenv()

# Steps:
# 1. Get the course ID to be published.
# 2. If the course exists, update it. If not, create a new course.
# 3. End the process.


def get_course_id_task(entry_id, **kwargs):
    """Fetch course ID from MongoDB"""
    mongo_client = AtlasClient()
    collection = "in_publishing_queue"
    entry = mongo_client.find(
        collection, filter={"_id": ObjectId(entry_id)})[0]
    return entry.get("course_id")


def update_course_task(course_id, **kwargs):
    """Update an existing course"""
    handle_update_course(course_id)
    return True


def create_course_task(course_id, **kwargs):
    """Create a new course"""
    handle_create_course(course_id)
    return True


def delete_entry_task(entry_id, **kwargs):
    """Delete the entry from the publishing queue"""
    mongo_client = AtlasClient()
    mongo_client.delete("in_publishing_queue", filter={
                        "_id": ObjectId(entry_id)})
    return True


def add_notification_task(course_id, **kwargs):
    """Add a notification for the user"""
    
    
    mongodb_client = AtlasClient()
    course = mongodb_client.find("courses", filter={"_id": ObjectId(course_id)})[0]
    users = course.get("users", [])
    message = f"The course {course['course_name']}."
    for user in users:
        notifications_object = {
            "username": user,
            "creation_date": datetime.now(timezone.utc).isoformat(),
            "type": "course",
            "message": message,
            "read": False,
            "project_id": course_id,
            "module_id": ""
        }
        mongodb_client.insert("notifications", notifications_object)
        
        notifications_object["state"] = f"Done"
        url = f"{os.getenv('FASTAPI_BACKEND_URL')}/task-complete"  # Adjust for your FastAPI host/port
        response = requests.post(_convert_object_ids_to_strings(url), json=notifications_object)
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
    entry = mongodb_client.find("in_publishing_queue", filter={"_id": ObjectId(entry_id)})

    if entry:

        course_id = entry[0].get("course_id")
        course = mongodb_client.find("course_design", filter={"_id": ObjectId(course_id)})[0]

        mongodb_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": {"status": "Publishing Failed"}})
        logging.info(f"Updated course {course_id} status to 'Failed' in MongoDB.")
        # Send failure notification
        message = f"Processing of the publishing for course {course['course_name']} failed. Please contact the administrator."
        users = course.get("users", [])
        for user in users:
            notification = {
                "username": user,
                "creation_date": datetime.now(timezone.utc).isoformat(),
                "type": "course",
                "message": message,
                "read": False,
                "project_id": course_id,
                "module_id": ""
            }
            mongodb_client.insert("notifications", notification)
            
            notification["state"] = f"Failed"
            url = f"{os.getenv('FASTAPI_BACKEND_URL')}/task-complete"  # Adjust for your FastAPI host/port
            response = requests.post(_convert_object_ids_to_strings(url), json=notification)
            response.raise_for_status()

        # Delete the entry from MongoDB
        mongodb_client.delete("in_publishing_queue", filter={"_id": ObjectId(entry_id)})
        logging.info(f"Deleted entry {entry_id} from MongoDB after failure.")

# Default Arguments
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": days_ago(1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "on_failure_callback": failure_callback
}

# Define the DAG
with DAG(
    "publishing_dag",
    default_args=default_args,
    description="DAG for processing the publishing queue entries",
    schedule_interval=None,  # Triggered externally
    catchup=False,
) as dag:

    start = EmptyOperator(task_id="start")

    get_course_id_step = PythonOperator(
        task_id="get_course_id",
        python_callable=get_course_id_task,
        provide_context=True,
        op_args=["{{ dag_run.conf.entry_id }}"]
    )

    def branch_on_course_id(**kwargs):
        """Determine whether to update or create a course"""
        ti = kwargs["ti"]  # TaskInstance context
        course_id = ti.xcom_pull(task_ids="get_course_id")

        if not course_id:
            return "end"  # If no course_id, skip to end

        mongo_client = AtlasClient()
        course = mongo_client.find(
            "courses", filter={"course_id": ObjectId(course_id)})

        if course:
            return "update_course"  # If course exists, update
        return "create_course"  # Otherwise, create

    branch = BranchPythonOperator(
        task_id="branch_on_course_id",
        python_callable=branch_on_course_id,
        provide_context=True
    )

    update_course_step = PythonOperator(
        task_id="update_course",
        python_callable=update_course_task,
        provide_context=True,
        op_args=["{{ ti.xcom_pull(task_ids='get_course_id') }}"]
    )

    create_course_step = PythonOperator(
        task_id="create_course",
        python_callable=create_course_task,
        provide_context=True,
        op_args=["{{ ti.xcom_pull(task_ids='get_course_id') }}"]
    )

    delete_entry_step = PythonOperator(
        task_id="delete_entry",
        python_callable=delete_entry_task,
        provide_context=True,
        op_args=["{{ dag_run.conf.entry_id }}"],
        trigger_rule=TriggerRule.ONE_SUCCESS
    )
    
    add_notification_step = PythonOperator(
        task_id="add_notification",
        python_callable=add_notification_task,
        provide_context=True,
        op_args=["{{ dag_run.conf.entry_id }}", "{{ ti.xcom_pull(task_ids='get_course_id') }}"]
    )    

    end = EmptyOperator(task_id="end")

    start >> get_course_id_step >> branch
    branch >> Label("Update Course") >> update_course_step
    branch >> Label("Create Course") >> create_course_step

    [update_course_step, create_course_step] >> delete_entry_step >> add_notification_step >> end
