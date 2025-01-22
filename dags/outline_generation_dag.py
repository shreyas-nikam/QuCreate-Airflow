from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from course.outline_generation import process_outline

def outline_generation_request(**kwargs):
    entry_id = kwargs["dag_run"].conf.get("entry_id")
    collection = kwargs["dag_run"].conf.get("collection")
    print(f"Processing entry with ID: {entry_id} from collection: {collection} for outline generation.")
    process_outline(entry_id)

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
    description='DAG for processing the outline generation queue entries',
    schedule_interval=None,  # Triggered externally
    catchup=False,
) as dag:
    outline_generation_request_task = PythonOperator(
        task_id='outline_generation_request',
        python_callable=outline_generation_request,
        provide_context=True,
    )
