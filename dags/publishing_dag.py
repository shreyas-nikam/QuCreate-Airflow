from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.utils.dates import days_ago
from airflow.operators.empty import EmptyOperator
from course.publishing import handle_update_course, handle_create_course
from utils.mongodb_client import AtlasClient
from bson.objectid import ObjectId
from airflow.utils.edgemodifier import Label

# Steps:
# 1. Get the course ID to be published.
# 2. If the course exists, update it. If not, create a new course.
# 3. End the process.


def get_course_id_task(entry_id, **kwargs):
    """Fetch course ID from MongoDB"""
    mongo_client = AtlasClient()
    collection = "in_publishing_queue"
    entry = mongo_client.find(
        collection, filter={"_id": ObjectId(entry_id)})[0]
    return entry.get("course_id")


def update_course_task(course_id, **kwargs):
    """Update an existing course"""
    handle_update_course(course_id)
    return True


def create_course_task(course_id, **kwargs):
    """Create a new course"""
    handle_create_course(course_id)
    return True


def delete_entry_task(entry_id, **kwargs):
    """Delete the entry from the publishing queue"""
    mongo_client = AtlasClient()
    mongo_client.delete("in_publishing_queue", filter={
                        "_id": ObjectId(entry_id)})
    return True


# Default Arguments
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": days_ago(1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
}

# Define the DAG
with DAG(
    "publishing_dag",
    default_args=default_args,
    description="DAG for processing the publishing queue entries",
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

    def branch_on_course_id(**kwargs):
        """Determine whether to update or create a course"""
        ti = kwargs["ti"]  # TaskInstance context
        course_id = ti.xcom_pull(task_ids="get_course_id")

        if not course_id:
            return "end"  # If no course_id, skip to end

        mongo_client = AtlasClient()
        course = mongo_client.find(
            "courses", filter={"course_id": ObjectId(course_id)})

        if course:
            return "update_course"  # If course exists, update
        return "create_course"  # Otherwise, create

    branch = BranchPythonOperator(
        task_id="branch_on_course_id",
        python_callable=branch_on_course_id,
        provide_context=True
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

    delete_entry_step = PythonOperator(
        task_id="delete_entry",
        python_callable=delete_entry_task,
        provide_context=True,
        op_args=["{{ dag_run.conf.entry_id }}"]
    )

    end = EmptyOperator(task_id="end")

    # ✅ FIXED Dependencies
    start >> get_course_id_step >> branch
    branch >> Label(
        "Update Course") >> update_course_step >> delete_entry_step >> end
    branch >> Label(
        "Create Course") >> create_course_step >> delete_entry_step >> end
