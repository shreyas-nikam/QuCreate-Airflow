from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Define the MongoDB connection details
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
MONGO_COLLECTION = "in_content_generation_queue"

# Define the Python function to process new entries
def process_new_entries(**kwargs):
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]

    # Check for new entries
    new_entries = list(collection.find())

    if not new_entries:
        print("No new entries found.")
        return

    for entry in new_entries:
        # Process each entry
        print(f"Processing entry: {entry}")
        # Call your custom function here
        process_entry(entry)

        # Delete the processed entry from the collection
        collection.delete_one({"_id": entry["_id"]})

    client.close()

def process_entry(entry):
    # Your custom processing logic goes here

    print(f"Processing entry: {entry}")

# Default arguments for the DAG
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# Define the DAG
dag = DAG(
    "mongodb_monitor_dag",
    default_args=default_args,
    description="A simple DAG to monitor MongoDB for new entries",
    schedule_interval=timedelta(minutes=1),  # Adjust schedule as needed
    start_date=datetime(2023, 1, 1),
    catchup=False,
)

# Define the PythonOperator
check_mongodb_task = PythonOperator(
    task_id="check_mongodb",
    python_callable=process_new_entries,
    dag=dag,
)

# Task pipeline
check_mongodb_task
