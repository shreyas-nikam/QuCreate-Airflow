from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from course.deliverables_generation import process_deliverables_request

def deliverables_generation(**kwargs):
    entry_id = kwargs["dag_run"].conf.get("entry_id")
    collection = kwargs["dag_run"].conf.get("collection")
    print(f"Processing entry with ID: {entry_id} from collection: {collection} for deliverables generation.")
    process_deliverables_request(entry_id)

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
    pass
    # deliverables_generation_task = PythonOperator(
    #     task_id='deliverables_generation',
    #     python_callable=deliverables_generation,
    #     provide_context=True,
    # )
