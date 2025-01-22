from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from course.publishing import publish_course

def process_publishing_request(**kwargs):
    entry_id = kwargs["dag_run"].conf.get("entry_id")
    collection = kwargs["dag_run"].conf.get("collection")
    print(f"Processing entry with ID: {entry_id} from collection: {collection} for publishing.")
    publish_course(entry_id)

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
    process_publishing_request_task = PythonOperator(
        task_id='process_publishing_request',
        python_callable=process_publishing_request,
        provide_context=True,
    )
