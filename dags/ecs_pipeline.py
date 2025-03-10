import time
import boto3
from botocore.exceptions import ClientError

# -------------------------------------------------------------------
# 1. CREATE (OR GET) AN ECS CLUSTER
# -------------------------------------------------------------------
def create_ecs_cluster_if_not_exists(cluster_name: str) -> str:
    """
    Creates an ECS cluster if it doesn't already exist.
    Returns the cluster ARN.
    """
    ecs_client = boto3.client("ecs")

    # Check if cluster exists
    try:
        existing = ecs_client.describe_clusters(clusters=[cluster_name])
        for cluster in existing["clusters"]:
            if cluster["clusterName"] == cluster_name:
                print(f"ECS cluster '{cluster_name}' already exists.")
                return cluster["clusterArn"]
    except ClientError as e:
        # If not found or other error, we attempt to create
        print(f"Cluster not found or error encountered: {e}")

    # Create cluster
    response = ecs_client.create_cluster(
        clusterName=cluster_name
    )
    cluster_arn = response["cluster"]["clusterArn"]
    print(f"Created ECS cluster: {cluster_name}")
    return cluster_arn

# -------------------------------------------------------------------
# 2. REGISTER TASK DEFINITION
# -------------------------------------------------------------------
def register_streamlit_task_definition(
    task_def_name: str,
    container_image: str,
    execution_role_arn: str = None,
    task_role_arn: str = None
) -> str:
    """
    Registers (or updates) a task definition for the Streamlit container.
    Returns the full task definition ARN.
    """

    ecs_client = boto3.client("ecs")

    container_def = {
        "name": "streamlit-app",
        "image": container_image,  # e.g. "<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/streamlit:latest"
        "essential": True,
        "portMappings": [
            {
                "containerPort": 8501,
                "protocol": "tcp"
            }
        ],
        # Optional environment variables, etc.
    }

    # A simple example of a FARGATE-compatible definition, 
    # but also works with EC2 if you remove the requires_compatibilities below.
    # For pure ECS-EC2, you do not need "requiresCompatibilities".
    # But let's show them in case you adapt for Fargate:
    register_kwargs = {
        "family": task_def_name,
        "networkMode": "bridge",  # For EC2 launch type
        "containerDefinitions": [container_def],
        "requiresCompatibilities": [],  # empty for EC2, ["FARGATE"] for Fargate
        "cpu": "256",
        "memory": "512",
    }
    if execution_role_arn:
        register_kwargs["executionRoleArn"] = execution_role_arn
    if task_role_arn:
        register_kwargs["taskRoleArn"] = task_role_arn

    response = ecs_client.register_task_definition(**register_kwargs)
    task_def_arn = response["taskDefinition"]["taskDefinitionArn"]
    print(f"Registered (or updated) task definition: {task_def_arn}")
    return task_def_arn

# -------------------------------------------------------------------
# 3. CREATE A SERVICE (EC2 LAUNCH TYPE)
# -------------------------------------------------------------------
def create_ecs_service(
    cluster_name: str,
    service_name: str,
    task_def_arn: str,
    desired_count: int = 1
) -> str:
    """
    Creates an ECS service with the specified cluster, service name,
    task definition, and desired count (for EC2 launch type).
    Returns the service ARN.
    """

    ecs_client = boto3.client("ecs")

    # If you have an ALB, you'd specify "loadBalancers" and "networkConfiguration" below.
    # This minimal example just uses the EC2 launch type with no ALB, 
    # so you must handle inbound traffic to the cluster's EC2 instance directly.

    try:
        response = ecs_client.create_service(
            cluster=cluster_name,
            serviceName=service_name,
            taskDefinition=task_def_arn,
            desiredCount=desired_count,
            launchType="EC2",
        )
        service_arn = response["service"]["serviceArn"]
        print(f"Created ECS service: {service_arn}")
        return service_arn
    except ClientError as e:
        if "ServiceAlreadyExistsException" in str(e):
            # If service already exists, update it
            print(f"Service {service_name} already exists, updating task definition.")
            update_resp = ecs_client.update_service(
                cluster=cluster_name,
                service=service_name,
                taskDefinition=task_def_arn,
                desiredCount=desired_count
            )
            return update_resp["service"]["serviceArn"]
        else:
            raise

# -------------------------------------------------------------------
# 4. WAIT FOR SERVICE STABILITY
# -------------------------------------------------------------------
def wait_for_service_stable(cluster_name: str, service_name: str, timeout: int = 300):
    """
    Wait until the ECS service reaches a stable state or the timeout is exceeded.
    """
    ecs_client = boto3.client("ecs")
    start_time = time.time()

    while True:
        response = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        service = response["services"][0]
        running_count = service["runningCount"]
        desired_count = service["desiredCount"]
        status = service["status"]

        if status == "ACTIVE" and running_count == desired_count:
            print(f"Service {service_name} is stable with {running_count}/{desired_count} tasks running.")
            break

        if time.time() - start_time > timeout:
            raise TimeoutError(f"Service {service_name} did not become stable in {timeout} seconds.")

        time.sleep(5)

# -------------------------------------------------------------------
# 5. GET EC2 INSTANCE INFO (FOR SSH) & PUBLIC IP
# -------------------------------------------------------------------
def get_ec2_container_instances(cluster_name: str):
    """
    Return the list of ECS container instances (ARNs) in the given cluster.
    (For EC2 launch type only.)
    """
    ecs_client = boto3.client("ecs")
    paginator = ecs_client.get_paginator("list_container_instances")

    container_instance_arns = []
    for page in paginator.paginate(cluster=cluster_name):
        container_instance_arns.extend(page["containerInstanceArns"])
    return container_instance_arns

def get_ec2_instance_details(cluster_name: str):
    """
    Get the underlying EC2 instance details for the ECS container instances in a cluster.
    Returns a list of dicts with { 'ec2_instance_id': ..., 'public_ip': ... }.
    """
    ecs_client = boto3.client("ecs")
    ec2_client = boto3.client("ec2")

    container_instance_arns = get_ec2_container_instances(cluster_name)
    if not container_instance_arns:
        print("No container instances found in cluster.")
        return []

    # Describe the container instances to get the EC2 instance IDs
    resp = ecs_client.describe_container_instances(
        cluster=cluster_name,
        containerInstances=container_instance_arns
    )
    ec2_instance_ids = [ci["ec2InstanceId"] for ci in resp["containerInstances"]]

    # Describe EC2 instances to get public IP / DNS info
    ec2_resp = ec2_client.describe_instances(
        InstanceIds=ec2_instance_ids
    )

    results = []
    for reservation in ec2_resp["Reservations"]:
        for instance in reservation["Instances"]:
            instance_id = instance["InstanceId"]
            public_ip = instance.get("PublicIpAddress")
            public_dns = instance.get("PublicDnsName")
            results.append({
                "ec2_instance_id": instance_id,
                "public_ip": public_ip,
                "public_dns": public_dns
            })
    return results

# -------------------------------------------------------------------
# 6. MAIN WORKFLOW FUNCTION (GLUE EVERYTHING TOGETHER)
# -------------------------------------------------------------------
def run_streamlit_ecs_workflow(
    cluster_name: str,
    service_name: str,
    task_def_name: str,
    container_image: str
):
    """
    A sample workflow that:
    1) Creates an ECS cluster
    2) Registers (or updates) a task definition
    3) Creates (or updates) an ECS service
    4) Waits for stability
    5) Fetches the underlying EC2 instance details
    6) Returns a "URL" for the user
    """

    # 1. Create ECS cluster if needed
    cluster_arn = create_ecs_cluster_if_not_exists(cluster_name)

    # 2. Register the task definition
    #    For demonstration, we don't pass execution_role_arn or task_role_arn.
    task_def_arn = register_streamlit_task_definition(
        task_def_name=task_def_name,
        container_image=container_image
    )

    # 3. Create ECS service
    service_arn = create_ecs_service(
        cluster_name=cluster_name,
        service_name=service_name,
        task_def_arn=task_def_arn,
        desired_count=1
    )

    # 4. Wait for the service to be stable
    wait_for_service_stable(cluster_name, service_name, timeout=300)

    # 5. Get the underlying EC2 instance info
    instance_details = get_ec2_instance_details(cluster_name)

    if not instance_details:
        print("No EC2 instances found for the ECS service. Can't provide a URL.")
        return None, None

    # For simplicity, assume there's only one instance running your container:
    ec2_info = instance_details[0]
    public_dns = ec2_info["public_dns"]
    instance_id = ec2_info["ec2_instance_id"]

    # If you haven't attached an ALB, you can directly connect via port 8501 on that EC2 instance
    # (assuming the Security Group allows inbound traffic on port 8501).
    # So the URL might be:
    url = f"http://{public_dns}:8501"

    # 6. Return or store the results
    print(f"Application is accessible at: {url}")
    print(f"EC2 instance ID: {instance_id} (for SSH).")

    # You might store these in a database, or return them to Airflow's XCom
    return url, ec2_info


if __name__ == "__main__":
    # Example usage (local test):
    cluster_name = "my-ecs-cluster"
    service_name = "my-streamlit-service"
    task_def_name = "my-streamlit-task"
    container_image = "123456789012.dkr.ecr.us-east-1.amazonaws.com/streamlit:latest"

    final_url, ec2_data = run_streamlit_ecs_workflow(
        cluster_name=cluster_name,
        service_name=service_name,
        task_def_name=task_def_name,
        container_image=container_image
    )

    if final_url:
        print(f"URL to access the application: {final_url}")
    if ec2_data:
        print(f"Developer can SSH into instance ID: {ec2_data['ec2_instance_id']}, Public IP: {ec2_data['public_ip']}")


from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime


default_args = {
    "owner": "airflow",
    "start_date": datetime(2023, 1, 1),
    # etc.
}

with DAG("ecs_streamlit_example_dag", default_args=default_args, schedule_interval=None) as dag:

    def launch_streamlit_app(**context):
        cluster_name = "my-ecs-cluster"
        service_name = "my-streamlit-service"
        task_def_name = "my-streamlit-task"
        container_image = "123456789012.dkr.ecr.us-east-1.amazonaws.com/streamlit:latest"

        url, ec2_info = run_streamlit_ecs_workflow(
            cluster_name=cluster_name,
            service_name=service_name,
            task_def_name=task_def_name,
            container_image=container_image
        )

        # Optionally push to XCom
        context["ti"].xcom_push(key="streamlit_url", value=url)
        context["ti"].xcom_push(key="ec2_info", value=ec2_info)

    run_task = PythonOperator(
        task_id="run_streamlit_ecs",
        python_callable=launch_streamlit_app,
        provide_context=True
    )

    run_task
