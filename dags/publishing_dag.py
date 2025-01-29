from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
import asyncio
from airflow.operators.empty import EmptyOperator
from course.publishing import _update_modules, handle_update_course, handle_create_course
from utils.mongodb_client import AtlasClient
from bson.objectid import ObjectId
from airflow.utils.edgemodifier import Label

# Steps:
# 1. Get the course id which is to be published.
# 2. Update the course if it exists. Create a new course if it doesn't.
# 3. Update the modules with the new resources.
# 4. Update the status of the course to "Published"


def get_course_id_task(entry_id, **kwargs):
    mongo_client = AtlasClient()
    collection = "in_publishing_queue"
    entry = mongo_client.get_document_by_id(collection, entry_id)
    course_id = entry.get("course_id")
    return course_id

def update_course_task(course_id, **kwargs):
    handle_update_course(course_id)
    return True

def create_course_task(course_id, **kwargs):
    handle_create_course(course_id)
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
    'publishing_dag',
    default_args=default_args,
    description='DAG for processing the publishing queue entries',
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

    def branch_on_course_id(course_id, **kwargs):
        mongo_client = AtlasClient()
        course = mongo_client.find("courses", filter={"course_id": ObjectId(course_id)})
        if course:
            return "update_course"
        return "create_course"
    
    branch = PythonOperator(
        task_id="branch_on_course_id",
        python_callable=branch_on_course_id,
        provide_context=True,
        op_args=["{{ ti.xcom_pull(task_ids='get_course_id') }}"]
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


    end = EmptyOperator(task_id="end")

    start >> get_course_id_step >> branch
    branch >> Label("Republish course") >> update_course_step >> end
    branch >> Label("Create Course") >> create_course_step >> end