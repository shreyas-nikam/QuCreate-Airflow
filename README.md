1. Install Libreoffice for converting ppt to pdf:

```bash
sudo apt update
sudo apt install libreoffice
# Check if soffice is installed by running soffice --version
npm install -g mermaid.cli
```

- Install claat


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
  GEMINI_MODEL=
  AZURE_TTS_SERVICE_REGION=
  AZURE_TTS_SPEECH_KEY=
  COHERE_API_KEY=
  PHOENIX_API_KEY=
  LLAMAPARSE_API_KEY=
  AIRFLOW_USERNAME=
  AIRFLOW_PASSWORD=
  VIMEO_ACCESS_TOKEN=
  VIMEO_CLIENT_SECRET=
  VIMEO_CLIENT_ID=
  GITHUB_USERNAME=
  GITHUB_TOKEN=
  FASTAPI_BACKEND_URL=
  AGENT_MODEL=
  AGENT_KEY=
  E2B_API_KEY=
  DOCKERHUB_USERNAME=
  DOCKERHUB_PASSWORD=
  ```

3. Install the required packages using `pip install -r requirements.txt`

   - Set the airflow home variable to current directory (Run `export AIRFLOW_HOME=$PWD)
   - Create username and password and store it in the environment variables

   ```
   airflow users  create --role Admin --username admin --email admin --firstname admin --lastname admin --password admin
   ```

3. Delete the md2pptx folder and git clone md2pptx inside the repo. `git clone https://github.com/MartinPacker/md2pptx.git`
4. Run `airflow db init` to initialize the database. Change the following lines in airflow.cfg file: auth_backends =auth.backend.basic_auth and load_examples=
5. Check if the dags folder is in the airflow home (Run `airflow dags list` to check).
6. Run airflow webserver (for development) (for deployment consider using pm2 `pm2 start "airflow webserver" --name webserver`)
7. Run airflow scheduler (for development) (for deployment, consider using pm2 `pm2 start "airflow scheduler" --name scheduler`)
8. Run `python mongodb_monitor` to run the sensor for detecting updates in the job queue. (for development) (for deployment consider using pm2 `pm2 start mongodb_monitor.py --interpreter /home/user1/QuCreate-Airflow/venv/bin/python --name monitor`)

8. For deployment, set up postgresql on port 5432. Create a user and grant permissions. (https://airflow.apache.org/docs/apache-airflow/stable/howto/set-up-database.html#setting-up-a-postgresql-database)
```
CREATE DATABASE airflow_db;
CREATE USER airflow_user WITH PASSWORD 'airflow_pass';
GRANT ALL PRIVILEGES ON DATABASE airflow_db TO airflow_user;
GRANT ALL ON SCHEMA public TO airflow_user;
```

9. For deployment, modify the airflow.cfg file's following parameters:
```
load_examples=False
sql_alchemy_conn=postgresql+psycopg2://<airflow_user>:<password>@localhost:5432/airflowdb
auth_backends=airflow.api.auth.backend.basic_auth
base_url=http://localhost:8080/airflow
```


Yet to be implemented:

1. Store all the files on s3 instead of storing it locally
2. Delete all files locally after done and pull it from s3 for the next run


FAQs:

1. Uninstall and install pymongo if you get bson error
2. Check airflow directory path if you do not see the dags
