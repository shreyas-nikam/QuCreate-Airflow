# Use the official Airflow image as the base (adjust the version as needed)
FROM apache/airflow:2.5.0

# Switch to root to install additional OS packages
USER root

# Install LibreOffice, Node.js, npm, and mermaid.cli
RUN apt-get update && \
    apt-get install -y libreoffice nodejs npm && \
    npm install -g @mermaid-js/mermaid-cli && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Switch back to the airflow user
USER airflow

# Set working directory to AIRFLOW_HOME (default: /opt/airflow)
WORKDIR ${AIRFLOW_HOME}

# Copy the requirements file and install any extra Python dependencies
COPY requirements.txt ${AIRFLOW_HOME}/
RUN pip install --no-cache-dir -r requirements.txt

# Copy your DAGs and other necessary files (e.g., mongodb_monitor.py)
COPY dags/ ${AIRFLOW_HOME}/dags/
COPY mongodb_monitor.py ${AIRFLOW_HOME}/

# Expose the Airflow webserver port
EXPOSE 8080

# Default command: start the webserver (can be overridden in docker-compose)
CMD ["airflow", "webserver"]
