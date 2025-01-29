from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from course.publishing import publish_course
import asyncio
from airflow.operators.empty import EmptyOperator
from course.publishing import _update_modules, handle_update_course, handle_create_course

# Steps:
# 1. Get the course id which is to be published.
# 2. Update the course if it exists. Create a new course if it doesn't.
# 3. Upda the modules with the new resources.
# 4. Update the status of the course to "Published"


def process_publishing_request(**kwargs):
    entry_id = kwargs["dag_run"].conf.get("entry_id")
    collection = "in_publishing_queue"
    print(f"Processing entry with ID: {entry_id} from collection: {collection} for publishing.")
    response = asyncio.run(publish_course(entry_id))
    print(response)

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': days_ago(1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
}

with DAG(
    'publishing_dag',
    default_args=default_args,
    description='DAG for processing the publishing queue entries',
    schedule_interval=None,  # Triggered externally
    catchup=False,
) as dag:
    pass
    # process_publishing_request_task = PythonOperator(
    #     task_id='process_publishing_request',
    #     python_callable=process_publishing_request,
    #     provide_context=True,
    # )
