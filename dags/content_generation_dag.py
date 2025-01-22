from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from course.content_generation import generate_content

def content_generation(**kwargs):
    entry_id = kwargs["dag_run"].conf.get("entry_id")
    collection = kwargs["dag_run"].conf.get("collection")
    print(f"Processing entry with ID: {entry_id} from collection: {collection} for content generation.")
    generate_content(entry_id)

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': days_ago(1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
}

with DAG(
    'content_generation_dag',
    default_args=default_args,
    description='DAG for generating content for the content generation queue entries',
    schedule_interval=None,  # Triggered externally
    catchup=False,
) as dag:
    content_generation_task = PythonOperator(
        task_id='content_generation',
        python_callable=content_generation,
        provide_context=True,
    )
