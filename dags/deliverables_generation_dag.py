import datetime
import ast
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.dates import days_ago
from course.deliverables_generation import _get_resources_link, _download_slide, _get_slide_content, _generate_video
from course.deliverables_generation import _get_transcript_from_ppt, _create_audio, _create_images, _create_videos, _generate_assessment, _generate_chatbot, upload_files, update_module_with_deliverables
import asyncio
import logging
from utils.mongodb_client import AtlasClient
from airflow.operators.python import BranchPythonOperator
from airflow.utils.edgemodifier import Label
from bson.objectid import ObjectId
from course.structure_generation import _get_course_and_module
from pathlib import Path
from airflow.utils.trigger_rule import TriggerRule
# Steps:
# 1. Get the course and module object from the course_id and module_id
# 2. Get the slide from the pre_processed_content
# 3. Generate the video from the slide
# 4. Extract the content from the slide
# 5. Create an assessment based on the content from the slide
# 6. Create a chatbot based on the content from the slide
# 7. Upload the video, assessment file, chatbot to s3
# 8. Update the module with the video, assessment, chatbot links in pre_processed_deliverables
# 9. Update the status of the course to Deliverables Review


def get_entry_from_mongo_step(entry_id, **kwargs):
    logging.info(f"Fetching entry with ID: {entry_id}")
    mongo_client = AtlasClient()
    entry = mongo_client.find("in_deliverables_generation_queue", filter={
                              "_id": ObjectId(entry_id)})
    if not entry:
        raise Exception(f"Entry with ID: {entry_id} not found.")
    course_id = entry[0].get("course_id")
    module_id = entry[0].get("module_id")
    voice_name = entry[0].get("voice_name")
    has_chatbot = entry[0].get("chatbot")
    course, module = _get_course_and_module(course_id, module_id)
    has_assessment = module.get("assessment")
    return course_id, module_id, voice_name, has_assessment, has_chatbot


def get_resources_link_step(course_id, module_id, **kwargs):
    slide_link, content_link = _get_resources_link(course_id, module_id)
    return slide_link, content_link


def download_slide_step(module_id, slide_link, **kwargs):
    download_slide_path = f"output/{module_id}"
    Path(download_slide_path).mkdir(parents=True, exist_ok=True)
    downloaded_slide_path = _download_slide(slide_link, download_slide_path)
    return downloaded_slide_path


def get_slide_content_step(content_link, **kwargs):
    slide_content = _get_slide_content(content_link)
    return slide_content


def get_transcript_step(downloaded_slide_path, **kwargs):
    transcript = _get_transcript_from_ppt(downloaded_slide_path)
    return transcript


def create_images_step(module_id, downloaded_slide_path, **kwargs):
    _create_images(downloaded_slide_path, module_id)


def create_audio_step(module_id, voice_name, transcript, **kwargs):
    print(transcript)
    print(type(transcript))
    transcript = ast.literal_eval(transcript)
    assert isinstance(transcript, list), "Transcript should be a list"
    logging.info(f"Creating audio for module: {
                 module_id}, voice: {voice_name}")
    _create_audio(module_id, transcript, voice_name)


def create_videos_step(module_id, **kwargs):
    _create_videos(module_id)
    return f"output/{module_id}/video.mp4"


def generate_assessment_step(slide_content, module_id, **kwargs):
    _generate_assessment(module_id, slide_content)
    assessment_file_path = f"output/{module_id}/questions.json"
    return assessment_file_path


def generate_chatbot_step(slide_content, course_id, module_id, **kwargs):
    destination = f"output/{module_id}/retriever"
    chatbot_link = asyncio.run(_generate_chatbot(
        slide_content, destination, course_id, module_id))
    return chatbot_link


def upload_files_step(course_id, video_path, assessment_file_path, chatbot_file_path, has_assessment, has_chatbot, module_id, **kwargs):
    video_link, assessment_link, chatbot_link = asyncio.run(upload_files(
        course_id, video_path, assessment_file_path, chatbot_file_path, module_id, has_assessment, has_chatbot))
    return video_link, assessment_link, chatbot_link


def update_module_with_deliverables_step(course_id, module_id, video_link, assessment_link, chatbot_link, has_chatbot, has_assessment, slide_link, **kwargs):
    update_module_with_deliverables(course_id, module_id, video_link,
                                    assessment_link, chatbot_link, has_chatbot, has_assessment, slide_link)
    return "Module updated with deliverables"


def delete_entry_from_mongodb_step(entry_id, **kwargs):
    logging.info(f"Deleting entry with ID: {entry_id}")
    mongo_client = AtlasClient()
    mongo_client.delete("in_deliverables_generation_queue",
                        filter={"_id": ObjectId(entry_id)})
    return "Entry deleted"


def add_notification_step(entry_id, course_id, module_id, **kwargs):

    _, module = _get_course_and_module(course_id, module_id)
    message = f"Module {module["module_name"]
                        } is ready for Deliverables Review."

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
    'deliverables_generation_dag',
    default_args=default_args,
    description='DAG for processing the deliverables generation queue entries',
    schedule_interval=None,
    catchup=False,
) as dag:

    start = EmptyOperator(task_id="start")

    get_entry_from_mongo_task = PythonOperator(
        task_id="get_entry_from_mongo",
        python_callable=get_entry_from_mongo_step,
        op_args=["{{ dag_run.conf['entry_id'] }}"],
        provide_context=True
    )

    # Dummy task to ensure upload_files only runs after all possible tasks
    join_task = EmptyOperator(
        task_id="join_task", trigger_rule=TriggerRule.ALL_DONE)

    def branch_logic(**kwargs):
        """Determines whether to execute assessment and chatbot generation tasks"""
        ti = kwargs['ti']
        entry_data = ti.xcom_pull(task_ids='get_entry_from_mongo')

        # Extract necessary fields
        _, _, _, has_assessment, has_chatbot = entry_data

        # Determine the next tasks dynamically
        next_tasks = []
        if has_assessment and has_chatbot:
            next_tasks.append("generate_assessment")
            next_tasks.append("generate_chatbot")
        elif has_assessment:
            next_tasks.append("generate_assessment")
        elif has_chatbot:
            next_tasks.append("generate_chatbot")
        else:
            # Ensure `join_task` always runs
            next_tasks.append("join_task")

        return next_tasks

    branch_task = BranchPythonOperator(
        task_id="branch_task",
        python_callable=branch_logic,
        provide_context=True
    )

    get_resources_link_task = PythonOperator(
        task_id="get_resources_link",
        python_callable=get_resources_link_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[1] }}"],
        provide_context=True
    )

    download_slide_task = PythonOperator(
        task_id="download_slide",
        python_callable=download_slide_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[1] }}",
                 "{{ task_instance.xcom_pull(task_ids='get_resources_link')[0] }}"],
        provide_context=True
    )

    get_slide_content_task = PythonOperator(
        task_id="get_slide_content",
        python_callable=get_slide_content_step,
        op_args=[
            "{{ task_instance.xcom_pull(task_ids='get_resources_link')[1] }}"],
        provide_context=True
    )

    get_transcript_task = PythonOperator(
        task_id="get_transcript",
        python_callable=get_transcript_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='download_slide') }}"],
        provide_context=True
    )

    create_images_task = PythonOperator(
        task_id="create_images",
        python_callable=create_images_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[1] }}",
                 "{{ task_instance.xcom_pull(task_ids='download_slide') }}"],
        provide_context=True
    )

    create_audio_task = PythonOperator(
        task_id="create_audio",
        python_callable=create_audio_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[1] }}",
                 "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[2] }}", "{{ task_instance.xcom_pull(task_ids='get_transcript') }}"],
        provide_context=True
    )

    create_videos_task = PythonOperator(
        task_id="create_videos",
        python_callable=create_videos_step,
        op_args=[
            "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[1] }}"],
        provide_context=True
    )

    generate_assessment_task = PythonOperator(
        task_id="generate_assessment",
        python_callable=generate_assessment_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='get_slide_content') }}",
                 "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[1] }}"],
        provide_context=True
    )

    generate_chatbot_task = PythonOperator(
        task_id="generate_chatbot",
        python_callable=generate_chatbot_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='get_slide_content') }}", "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[1] }}"],
        provide_context=True
    )

    upload_files_task = PythonOperator(
        task_id="upload_files",
        python_callable=upload_files_step,
        op_args=[
            "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[0] }}",
            "{{ task_instance.xcom_pull(task_ids='create_videos') }}",
            "{{ task_instance.xcom_pull(task_ids='generate_assessment') if task_instance.xcom_pull(task_ids='generate_assessment') else '' }}",
            "{{ task_instance.xcom_pull(task_ids='generate_chatbot') if task_instance.xcom_pull(task_ids='generate_chatbot') else '' }}",
            "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[3] }}",
            "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[4] }}",
            "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[1] }}"
        ],
        provide_context=True
    )

    update_module_with_deliverables_task = PythonOperator(
        task_id="update_module_with_deliverables",
        python_callable=update_module_with_deliverables_step,
        op_args=["{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[1] }}",
                 "{{ task_instance.xcom_pull(task_ids='upload_files')[0] }}",
                 "{{ task_instance.xcom_pull(task_ids='upload_files')[1] }}",
                 "{{ task_instance.xcom_pull(task_ids='upload_files')[2] }}",
                 "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[4] }}",
                 "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[3] }}",
                 "{{ task_instance.xcom_pull(task_ids='get_resources_link')[0] }}",
                 ],
        provide_context=True
    )

    delete_entry_from_mongo_task = PythonOperator(
        task_id="delete_entry_from_mongo",
        python_callable=delete_entry_from_mongodb_step,
        op_args=[
            "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[0] }}"],
        provide_context=True
    )

    add_notification_task = PythonOperator(
        task_id="add_notification",
        python_callable=add_notification_step,
        op_args=[
            "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[0] }}",
            "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[0] }}",
            "{{ task_instance.xcom_pull(task_ids='get_entry_from_mongo')[1] }}"
        ],
        provide_context=True
    )

    end = EmptyOperator(task_id="end")

    # Task dependencies
    start >> get_entry_from_mongo_task >> get_resources_link_task >> download_slide_task >> get_slide_content_task >> get_transcript_task >> create_images_task >> create_audio_task >> create_videos_task >> branch_task

    branch_task >> Label("Run Assessment") >> generate_assessment_task
    branch_task >> Label("Run Chatbot") >> generate_chatbot_task
    [generate_assessment_task, generate_chatbot_task] >> join_task

    branch_task >> Label("Skip Assessment and Chatbot") >> join_task

    # Ensure upload_files_task runs only after all preceding tasks
    join_task >> upload_files_task >> update_module_with_deliverables_task >> delete_entry_from_mongo_task >> add_notification_task >> end
