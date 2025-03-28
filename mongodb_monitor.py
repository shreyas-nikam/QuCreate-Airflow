from pymongo import MongoClient
import os
import threading
import requests
from dotenv import load_dotenv

load_dotenv()

# MongoDB Connection Details
MONGO_URI = os.getenv("MONGO_URI")
# MongoDB Atlas Connection Details
DATABASE_NAME = os.getenv("MONGO_DB")

# Collections and Their Corresponding Airflow DAGs
COLLECTIONS_TO_DAGS = {
    "in_outline_generation_queue": "outline_generation_dag",
    "in_content_generation_queue": "content_generation_dag",
    "in_structure_generation_queue": "structure_generation_dag",
    "in_deliverables_generation_queue": "deliverables_generation_dag",
    "in_publishing_queue": "publishing_dag",
    "in_lab_generation_queue": "lab_generation_dag",
}

# Airflow REST API Authentication
AIRFLOW_BASE_URL = "http://localhost:8080/api/v1"
AIRFLOW_AUTH = (os.getenv("AIRFLOW_USERNAME"), os.getenv("AIRFLOW_PASSWORD"))  # Replace with your Airflow username/password

def trigger_airflow_dag(dag_id, entry_id, collection_name):
    """Trigger an Airflow DAG run via REST API."""
    try:
        response = requests.post(
            f"{AIRFLOW_BASE_URL}/dags/{dag_id}/dagRuns",
            auth=AIRFLOW_AUTH,
            json={"conf": {"entry_id": entry_id, "collection": collection_name}},  # Pass entry ID and collection name
        )
        if response.status_code == 200:
            print(f"Successfully triggered DAG '{dag_id}' for entry_id: {entry_id} from {collection_name}")
        else:
            print(f"Failed to trigger DAG '{dag_id}': {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Error triggering DAG '{dag_id}': {e}")

def watch_collection(collection_name, dag_id):
    """Watch a MongoDB collection for changes and trigger its corresponding Airflow DAG."""
    client = MongoClient(MONGO_URI)
    db = client[DATABASE_NAME]
    collection = db[collection_name]

    print(f"Watching MongoDB collection '{collection_name}' for new entries.")

    with collection.watch() as stream:
        for change in stream:
            if change["operationType"] == "insert":
                entry_id = str(change["documentKey"]["_id"])  # Extract the ID of the new document
                print(f"New entry detected in {collection_name}: {entry_id}")
                trigger_airflow_dag(dag_id, entry_id, collection_name)

def main():
    """Start watching multiple MongoDB collections and trigger DAGs."""
    threads = []
    for collection_name, dag_id in COLLECTIONS_TO_DAGS.items():
        thread = threading.Thread(target=watch_collection, args=(collection_name, dag_id))
        thread.start()
        threads.append(thread)

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

if __name__ == "__main__":
    main()


