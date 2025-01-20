Steps to run the DAG

1. Install Airflow using `pip install apache-airflow`
2. Create a virtual environment using `python3 -m venv .venv`
3. Install the required packages using `pip install -r requirements.txt`
4. Run `airflow db init` to initialize the database
5. Check if the dags folder is in the airflow home (Run `airflow dags list` to check)
6. Run airflow webserver
7. Run airflow scheduler
8. Check if the DAG is running.



