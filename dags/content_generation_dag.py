import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.dates import days_ago
from course.content_generation import fetch_outline
from course.helper import get_slides, get_module_information
import logging
from utils.s3_file_manager import S3FileManager
from utils.mongodb_client import AtlasClient
from bson.objectid import ObjectId
from course.content_generation import _get_course_and_module
import asyncio
from pathlib import Path
import json
import ast

# Steps:
# 1. Fetch the outline for the module from mongodb.
# 2. Generate the content for the slides and module information.
# 3. Write the content to a file and the module information as well.
# 4. Upload the file to s3.
# 5. Update mongodb with new resources.
# 6. Update the status of the module to "Content Review".


def fetch_details_from_mongo(entry_id, **kwargs):
    logging.info(f"Fetching details for entry with ID: {entry_id}")
    entry_id = kwargs["dag_run"].conf.get("entry_id")
    mongodb_client = AtlasClient()
    entry = mongodb_client.find("in_content_generation_queue", filter={
                                "_id": ObjectId(entry_id)})
    if not entry:
        return "Entry not found"

    entry = entry[0]
    course_id = entry.get("course_id")
    module_id = entry.get("module_id")

    return course_id, module_id


def fetch_outline_step(course_id, module_id, **kwargs):
    outline = fetch_outline(course_id, module_id)
    logging.info(f"Outline for module: {module_id} is: {outline}")
    return outline


def generate_slides_step(module_id, outline, **kwargs):
    logging.info(f"Generating slides for module: {module_id}")
    slides = asyncio.run(get_slides(module_id, outline))
    logging.info(f"Slides generated: {slides}")
    return slides


def generate_module_information_step(module_id, slides, **kwargs):
    logging.info(f"Generating module information for module: {module_id}")
    module_information = asyncio.run(get_module_information(module_id, slides))
    logging.info(f"Module information generated: {module_information}")
    return module_information


def write_content_to_file_step(module_id, slides, module_information, **kwargs):
    logging.info(f"Writing content to file for module: {module_id}")
    slide_output_path = f"output/{module_id}/slide_content/slide_content.json"
    module_information_output_path = f"output/{module_id}/module_information/module_information.md"
    python_data = ast.literal_eval(slides)
    json_data = json.dumps(python_data, indent=4)
    Path(slide_output_path[:slide_output_path.rindex("/")]
         ).mkdir(parents=True, exist_ok=True)
    with open(slide_output_path, "w") as slide_file:
        json.dump(python_data, slide_file, indent=4)
    Path(module_information_output_path[:module_information_output_path.rindex(
        "/")]).mkdir(parents=True, exist_ok=True)
    with open(module_information_output_path, "w") as module_information_file:
        module_information_file.write(module_information)
    logging.info(f"Content written to file for module: {module_id}")
    return slide_output_path, module_information_output_path


def upload_content_to_s3_step(course_id, module_id, slide_output_path, module_information_output_path, **kwargs):
    logging.info(f"Uploading content to s3 for module: {module_id}")
    s3_file_manager = S3FileManager()
    s3_slide_output_key = f"qu-course-design/{course_id}/{module_id}/slide_content/slide_content.json"
    s3_module_information_output_key = f"qu-course-design/{course_id}/{module_id}/module_information/module_information.md"
    asyncio.run(s3_file_manager.upload_file(
        slide_output_path, s3_slide_output_key))
    asyncio.run(s3_file_manager.upload_file(
        module_information_output_path, s3_module_information_output_key))
    logging.info(f"Content uploaded to s3 for module: {module_id}")
    slide_output_link = "https://qucoursify.s3.us-east-1.amazonaws.com/" + s3_slide_output_key
    module_information_output_link = "https://qucoursify.s3.us-east-1.amazonaws.com/" + \
        s3_module_information_output_key
    return slide_output_link, module_information_output_link


def update_mongodb_with_resources_step(course_id, module_id, slide_output_link, module_information_output_link, **kwargs):
    logging.info(f"Updating mongodb with resources for module: {module_id}")
    mongodb_client = AtlasClient()
    course, module = _get_course_and_module(course_id, module_id)

    if not course or not module:
        raise Exception("Course or Module not found")

    module["pre_processed_content"] = []

    slide_resource = {
        "resource_type": "Slide_Content",
        "resource_name": "Slide Content",
        "resource_description": "Slide content generated using AI",
        "resource_link": slide_output_link,
        "resource_id": ObjectId()
    }
    module["pre_processed_content"].append(slide_resource)
    module_info_resource = {
        "resource_type": "Note",
        "resource_name": "Module Information",
        "resource_description": "Module Information generated using AI",
        "resource_link": module_information_output_link,
        "resource_id": ObjectId()
    }
    module["pre_processed_content"].append(module_info_resource)
    module["status"] = "Content Review"
    course["modules"] = [module if m.get("module_id") == ObjectId(module_id) else m for m in course.get("modules", [])]
    mongodb_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={
        "$set": {"modules": course["modules"]}
    })
    logging.info(f"Resources updated in mongodb for module: {module_id}")
    return "Content generated successfully"


def delete_entry_from_mongo_step(entry_id, **kwargs):
    logging.info(f"Deleting entry from MongoDB for entry_id: {entry_id}")
    mongodb_client = AtlasClient()
    mongodb_client.delete("in_content_generation_queue",
                          filter={"_id": ObjectId(entry_id)})
    logging.info(f"Entry deleted from MongoDB for entry_id: {entry_id}")
    return "Entry deleted successfully"


def add_notification_step(entry_id, course_id, module_id, **kwargs):

    course, module = _get_course_and_module(course_id, module_id)
    message = f"Module {module['module_name']} is ready for Content Review."

    users = course.get("users", [])
    mongodb_client = AtlasClient()
    for user in users:
        notifications_object = {
            "username": user,
            "creation_date": datetime.datetime.now(),
            "type": "course_module",
            "message": message,
            "read": False,
            "module_id": module_id,
            "project_id": course_id
        }
        mongodb_client.insert("notifications", notifications_object)

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
    entry = mongodb_client.find("in_content_generation_queue", filter={"_id": ObjectId(entry_id)})

    if entry:

        course_id = entry[0].get("course_id")
        module_id = entry[0].get("module_id")
        course, module = _get_course_and_module(course_id, module_id)

        for index, module in enumerate(course['modules']):
            if module['module_id'] == ObjectId(module_id):
                course['modules'][index]['status'] = 'Failed'
                break

        mongodb_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": {"modules": course["modules"]}})
        logging.info(f"Updated course {course_id} with failed status for module {module_id}")
        # Send failure notification
        message = f"Processing of the content for module {module['module_name']} failed. Please contact the administrator."
        users = course.get("users", [])
        for user in users:
            notification = {
                "username": user,
                "creation_date": datetime.datetime.now(),
                "type": "course_module",
                "message": message,
                "read": False,
                "module_id": module_id,
                "project_id": course_id
            }
            mongodb_client.insert("notifications", notification)

        # Delete the entry from MongoDB
        mongodb_client.delete("in_content_generation_queue", filter={"_id": ObjectId(entry_id)})
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
    'content_generation_dag',
    default_args=default_args,
    description='DAG for generating content for the content generation queue entries',
    schedule_interval=None,  # Triggered externally
    catchup=False,
) as dag:

    start = EmptyOperator(task_id="start")

    # Fetch the entry from MongoDB
    fetch_entry = PythonOperator(
        task_id='fetch_entry_from_mongo',
        python_callable=fetch_details_from_mongo,
        # Pass entry_id from the dag run
        op_args=["{{ dag_run.conf['entry_id'] }}"],
        provide_context=True
    )

    fetch_outline_task = PythonOperator(
        task_id='fetch_outline',
        python_callable=fetch_outline_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}"],
        provide_context=True
    )

    generate_slides_task = PythonOperator(
        task_id='generate_slides',
        python_callable=generate_slides_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_outline') }}"],
        provide_context=True
    )

    generate_module_information_task = PythonOperator(
        task_id='generate_module_information',
        python_callable=generate_module_information_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}",
                 "{{ task_instance.xcom_pull(task_ids='generate_slides') }}"],
        provide_context=True
    )

    write_content_to_file_task = PythonOperator(
        task_id='write_content_to_file',
        python_callable=write_content_to_file_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}", "{{ task_instance.xcom_pull(task_ids='generate_slides') }}",
                 "{{ task_instance.xcom_pull(task_ids='generate_module_information') }}"],
        provide_context=True
    )

    upload_content_to_s3_task = PythonOperator(
        task_id='upload_content_to_s3',
        python_callable=upload_content_to_s3_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[0] }}", "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}",
                 "{{ task_instance.xcom_pull(task_ids='write_content_to_file')[0] }}", "{{ task_instance.xcom_pull(task_ids='write_content_to_file')[1] }}"],
        provide_context=True
    )

    update_mongodb_with_resources_task = PythonOperator(
        task_id='update_mongodb_with_resources',
        python_callable=update_mongodb_with_resources_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[0] }}", "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}",
                 "{{ task_instance.xcom_pull(task_ids='upload_content_to_s3')[0] }}", "{{ task_instance.xcom_pull(task_ids='upload_content_to_s3')[1] }}"],
        provide_context=True
    )

    delete_entry_from_mongo_task = PythonOperator(
        task_id='delete_entry_from_mongo',
        python_callable=delete_entry_from_mongo_step,
        op_args=[
            "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[0] }}"],
        provide_context=True
    )
    
    add_notification_task = PythonOperator(
        task_id='add_notification',
        python_callable=add_notification_step,
        op_args=["{{ dag_run.conf['entry_id'] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_entry_from_mongo')[1] }}"],
        provide_context=True
    )

    end = EmptyOperator(task_id="end")

    start >> fetch_entry >> fetch_outline_task >> generate_slides_task >> generate_module_information_task >> write_content_to_file_task >> upload_content_to_s3_task >> update_mongodb_with_resources_task >> delete_entry_from_mongo_task >> add_notification_task >> end
