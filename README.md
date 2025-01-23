Install Libreoffice for converting ppt to pdf:
```bash
sudo apt update
sudo apt install libreoffice
```


Steps to run the DAG

1. Install Airflow using `pip install apache-airflow`
 - Create username and password and store it in the environment variables 
2. Create a virtual environment using `python3 -m venv .venv`
 - Create .env file with the following variables:
    ```
    MONGO_URI=
    MONGO_DB=
    AWS_ACCESS_KEY=
    AWS_SECRET_KEY=
    AWS_BUCKET_NAME=
    OPENAI_KEY=
    OPENAI_MODEL=
    GEMINI_API_KEY=
    AZURE_TTS_SERVICE_REGION=
    AZURE_TTS_SPEECH_KEY=
    TAVILY_API_KEY=
    COHERE_API_KEY=
    PHOENIX_API_KEY=
    LLAMAPARSE_API_KEY=
    AIRFLOW_USERNAME=
    AIRFLOW_PASSWORD=
    ```
3. Install the required packages using `pip install -r requirements.txt`
4. Run `airflow db init` to initialize the database
5. Check if the dags folder is in the airflow home (Run `airflow dags list` to check)
6. Run airflow webserver
7. Run airflow scheduler
8. Run `python mongodb_monitor` to run the sensor for detecting updates in the job queue.




For deploying:
1. pip freeze > requirements.txt


