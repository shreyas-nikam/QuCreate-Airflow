1. Install Libreoffice for converting ppt to pdf:

```bash
sudo apt update
sudo apt install libreoffice
```

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

   - Set the airflow home variable to current directory (Run `export AIRFLOW_HOME=$PWD` and `echo $AIRFLOW_HOME`)
   - Create username and password and store it in the environment variables

   ```
   airflow users  create --role Admin --username admin --email admin --firstname admin --lastname admin --password admin
   ```
3. Delte the md2pptx folder and git clone md2pptx inside the repo.
4. Run `airflow db init` to initialize the database. Change the following line in airflow.cfg file: auth_backends = airflow.api.auth.backend.basic_auth
5. Check if the dags folder is in the airflow home (Run `airflow dags list` to check).
6. Run airflow webserver
7. Run airflow scheduler
8. Run `python mongodb_monitor` to run the sensor for detecting updates in the job queue.

For deploying:

1. pip freeze > requirements.txt

Yet to be implemented:

1. Store all the files on s3 instead of storing it locally
2. Delete all files locally after done and pull it from s3 for the next run
3. Delete the ids from queue if completed execution
4. Retry if failed or notify developer of failed task

FAQs:

1. Uninstall and install pymongo if you get bson error
2. Check airflow directory path if you do not see the dags
