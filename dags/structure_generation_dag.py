from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from course.structure_generation import process_structure_request
import asyncio

def process_structure_generation_request(**kwargs):
    entry_id = kwargs["dag_run"].conf.get("entry_id")
    collection = "in_structure_generation_queue"
    print(f"Processing entry with ID: {entry_id} from collection: {collection} for structure generation.")
    response = asyncio.run(process_structure_request(entry_id))
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
    'structure_generation_dag',
    default_args=default_args,
    description='DAG for processing the structure generation queue entries',
    schedule_interval=None,  # Triggered externally
    catchup=False,
) as dag:
    pass
    process_structure_generation_request_task = PythonOperator(
        task_id='process_structure_generation_request',
        python_callable=process_structure_generation_request,
        provide_context=True,
    )
