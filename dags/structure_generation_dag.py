import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from course.structure_generation import process_structure_request
import asyncio
from airflow.operators.empty import EmptyOperator
from course.structure_generation import _get_course_and_module, _get_resource_link, _extract_content, _generate_pptx, _add_transcript_to_pptx, _save_file_to_s3, _update_slide_entry

# Steps:
# 1. Fetch the entry from mongodb.
# 2. Get course and module for the entry.
# 3. Get resource link for the slide content
# 4. Extract markdown and transcript from the file.
# 5. Write it to a md file
# 6. Convert it into a ppt
# 7. Add transcript to ppt
# 8. upload it to s3
# 9. Update the mongodb with the new resources.
# 10. Update the status of the course to "Structure Review"
from utils.mongodb_client import AtlasClient
from bson.objectid import ObjectId
import logging
from utils.s3_file_manager import S3FileManager


def fetch_details_from_mongo_task(entry_id, **kwargs):
    logging.info(f"Fetching details for entry with ID: {entry_id}")
    entry_id = kwargs["dag_run"].conf.get("entry_id")
    mongodb_client = AtlasClient()
    entry = mongodb_client.find("in_structure_generation_queue", filter={
                                "_id": ObjectId(entry_id)})
    if not entry:
        return "Entry not found"

    entry = entry[0]
    course_id = entry.get("course_id")
    module_id = entry.get("module_id")

    return course_id, module_id


def get_resource_link_task(course_id, module_id, **kwargs):
    _, module = _get_course_and_module(course_id, module_id)
    slide_content_link = _get_resource_link(module)
    module_name = module.get("module_name")
    return module_name, slide_content_link


def extract_content_task(module_name, slide_content_link, **kwargs):
    slide_content_key = slide_content_link.split(
        "/")[3] + "/" + "/".join(slide_content_link.split("/")[4:])
    logging.info(f"Extracting content from: {slide_content_key}")
    markdown, transcript = _extract_content(module_name, slide_content_key)
    return markdown, transcript


def generate_pptx_task(markdown, module_id, **kwargs):
    pptx_file_path = _generate_pptx(markdown, module_id)
    return pptx_file_path


def add_transcript_to_pptx_task(pptx_file_path, transcript, **kwargs):
    pptx_file = _add_transcript_to_pptx(pptx_file_path, transcript)
    return pptx_file


def save_file_to_s3_task(pptx_file, course_id, module_id, **kwargs):
    key = f"qu-course-design/{course_id}/{module_id}/structure.pptx"
    resource_link = asyncio.run(_save_file_to_s3(pptx_file, key))
    return resource_link


def update_slide_entry_task(course_id, module_id, resource_link, **kwargs):
    return _update_slide_entry(course_id, module_id, resource_link)


def delete_entry_from_mongodb_task(course_id, module_id, **kwargs):
    logging.info("Deleting entry from MongoDB")
    mongodb_client = AtlasClient()
    mongodb_client.delete("in_structure_generation_queue", filter={
                          "course_id": course_id, "module_id": module_id})
    logging.info("Entry deleted")
    return True


def add_notification_task(entry_id, course_id, module_id, **kwargs):

    _, module = _get_course_and_module(course_id, module_id)
    message = f"Module {module["module_name"]} is ready for Structure Review."

    mongodb_client = AtlasClient()
    notifications_object = {
        "username": "eca33ce0-62e5-41f8-88b0-1cf558fa7c81",
        "creation_date": datetime.datetime.now(),
        "type": "course_module",
        "message": message,
        "read": False,
        "module_id": module_id,
        "project_id": course_id
    }
    mongodb_client.insert("notifications", notifications_object)

    return True


default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': days_ago(1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
}

with DAG(
    'structure_generation_dag',
    default_args=default_args,
    description='DAG for processing the structure generation queue entries',
    schedule_interval=None,  # Triggered externally
    catchup=False,
) as dag:

    start = EmptyOperator(task_id="start")

    # Fetch the entry from MongoDB
    logging.info("Fetching details from MongoDB")
    fetch_details_from_mongo_step = PythonOperator(
        task_id='fetch_details_from_mongo',
        python_callable=fetch_details_from_mongo_task,
        op_args=["{{ dag_run.conf.entry_id }}"],
        provide_context=True
    )

    # Get resource link for the slide content
    logging.info("Getting resource link")
    get_resource_link_step = PythonOperator(
        task_id='get_resource_link',
        python_callable=get_resource_link_task,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_details_from_mongo')[1] }}"],
        provide_context=True
    )

    # Extract markdown and transcript from the file
    logging.info("Extracting content")
    extract_content_step = PythonOperator(
        task_id='extract_content',
        python_callable=extract_content_task,
        op_args=["{{ task_instance.xcom_pull(task_ids='get_resource_link')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='get_resource_link')[1] }}"],
        provide_context=True
    )

    # Generate pptx
    logging.info("Generating pptx")
    generate_pptx_step = PythonOperator(
        task_id='generate_pptx',
        python_callable=generate_pptx_task,
        op_args=["{{ task_instance.xcom_pull(task_ids='extract_content')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_details_from_mongo')[1] }}"],
        provide_context=True
    )

    # Add transcript to pptx
    logging.info("Adding transcript to pptx")
    add_transcript_to_pptx_step = PythonOperator(
        task_id='add_transcript_to_pptx',
        python_callable=add_transcript_to_pptx_task,
        op_args=["{{ task_instance.xcom_pull(task_ids='generate_pptx') }}",
                 "{{ task_instance.xcom_pull(task_ids='extract_content')[1] }}"],
        provide_context=True
    )

    # Save file to s3
    logging.info("Saving file to s3")
    save_file_to_s3_step = PythonOperator(
        task_id='save_file_to_s3',
        python_callable=save_file_to_s3_task,
        op_args=["{{ task_instance.xcom_pull(task_ids='add_transcript_to_pptx') }}", "{{ task_instance.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_details_from_mongo')[1] }}"],
        provide_context=True
    )

    # Update slide entry
    logging.info("Updating slide entry")
    update_slide_entry_step = PythonOperator(
        task_id='update_slide_entry',
        python_callable=update_slide_entry_task,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_details_from_mongo')[1] }}", "{{ task_instance.xcom_pull(task_ids='save_file_to_s3') }}"],
        provide_context=True
    )

    delete_entry_from_mongodb_step = PythonOperator(
        task_id="delete_entry_from_mongodb",
        python_callable=delete_entry_from_mongodb_task,
        op_args=["{{ task_instance.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_details_from_mongo')[1] }}"],
        provide_context=True
    )

    add_notification_step = PythonOperator(
        task_id="add_notification",
        python_callable=add_notification_task,
        op_args=["{{ dag_run.conf.entry_id }}", "{{ task_instance.xcom_pull(task_ids='fetch_details_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='fetch_details_from_mongo')[1] }}"],
        provide_context=True
    )

    end = EmptyOperator(task_id="end")

    start >> fetch_details_from_mongo_step >> get_resource_link_step >> extract_content_step >> generate_pptx_step >> add_transcript_to_pptx_step >> save_file_to_s3_step >> update_slide_entry_step >> delete_entry_from_mongodb_step >> add_notification_step >> end
