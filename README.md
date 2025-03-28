# QuCreate Airflow Setup

## Development Steps

1. **Install LibreOffice & Mermaid CLI**  
   ```bash
   sudo apt update
   sudo apt install libreoffice
   # Check if soffice is installed by running:
   soffice --version

   # Install mermaid.cli globally (requires Node.js / npm):
   npm install -g mermaid.cli

   # Check installation
   mmdc --version
   ```

2. **Install PostgreSQL (optional for local dev if you want to use Postgres instead of SQLite)**  
   ```bash
   sudo apt update
   sudo apt install postgresql postgresql-contrib
   ```
   - After installation, you can start/restart the PostgreSQL service (often via `sudo service postgresql start` or `systemctl start postgresql`).

4. **Create a virtual environment**  
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

5. **Create a `.env` file**  
   Populate it with the following variables:
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

6. **Install the required Python packages**  
   ```bash
   pip install -r requirements.txt
   ```

7. **Set Airflow environment variables and initialize**  
   - Set the `AIRFLOW_HOME` variable to the current directory:
     ```bash
     export AIRFLOW_HOME=$PWD
     ```
   - Initialize the Airflow database:
     ```bash
     airflow db init
     ```
   - In your **airflow.cfg**, modify:
     - `auth_backends = airflow.api.auth.backend.basic_auth`
     - `load_examples = False` (optional for a clean environment)

8. **Create an Airflow user**  
   ```bash
   airflow users create \
     --role Admin \
     --username admin \
     --email admin \
     --firstname admin \
     --lastname admin \
     --password admin
   ```

9. **Check if the `dags` folder is recognized**  
   ```bash
   airflow dags list
   ```
   Ensure the folder containing your DAGs is under `$AIRFLOW_HOME/dags` or configured in `airflow.cfg`.

10. **Run the Airflow webserver & scheduler (Development)**  
   ```bash
   # In one terminal:
   airflow webserver
   
   # In another terminal:
   airflow scheduler
   ```
   Or, if you want to keep them running in the background (still for development), you can use something like [pm2](https://pm2.keymetrics.io/):
   ```bash
   pm2 start "airflow webserver" --name webserver
   pm2 start "airflow scheduler" --name scheduler
   ```

11. **Run the MongoDB monitor**  
   This sensor detects updates in the job queue:
   ```bash
   python mongodb_monitor.py
   ```
   For production-like background service (still on dev machine), you can do:
   ```bash
   pm2 start mongodb_monitor.py \
      --interpreter /path/to/QuCreate-Airflow/.venv/bin/python \
      --name monitor
   ```

---

## Deployment Steps

1. **Set up PostgreSQL (instead of SQLite)**  
   You may already have installed PostgreSQL (see step above). Next, create a DB & user:  
   ```sql
   CREATE DATABASE airflow_db;
   CREATE USER airflow_user WITH PASSWORD 'airflow_pass';
   GRANT ALL PRIVILEGES ON DATABASE airflow_db TO airflow_user;
   GRANT ALL ON SCHEMA public TO airflow_user;
   ```
   Ensure PostgreSQL is running on port `5432`.  

2. **Adjust `airflow.cfg` for Production**  
   In your `airflow.cfg`, set:
   ```
   load_examples = False
   sql_alchemy_conn = postgresql+psycopg2://<airflow_user>:<password>@localhost:5432/airflow_db
   auth_backends = airflow.api.auth.backend.basic_auth
   base_url = http://localhost:8080/airflow
   ```

4. **Store `AIRFLOW_HOME` in your bashrc**  
   ```bash
   nano ~/.bashrc
   # Add the line:
   export AIRFLOW_HOME=/path/to/QuCreate-Airflow
   source ~/.bashrc
   ```

5. **Use pm2 (or systemd, Supervisor, etc.) for Airflow services**  
   Instead of running everything in the foreground, manage them in the background:
   ```bash
   pm2 start "airflow webserver" --name webserver
   pm2 start "airflow scheduler" --name scheduler
   pm2 start mongodb_monitor.py \
      --interpreter </path/to/QuCreate-Airflow/>.venv/bin/python \
      --name monitor
   ```


---

## Yet To Be Implemented

1. Storing all output files on S3 instead of locally.  
2. Deleting all local files after a run and pulling from S3 for the next run.

---

## FAQs

1. **BSON error with `pymongo`:**  
   - Uninstall and reinstall `pymongo` if you encounter BSON-related import errors.
     ```bash
     pip uninstall pymongo
     pip install pymongo
     ```

2. **Missing DAGs:**  
   - If you do not see DAGs when you run `airflow dags list`, ensure your `dags_folder` path in `airflow.cfg` (or your `$AIRFLOW_HOME/dags`) is correct and that your DAG Python files are indeed there.
