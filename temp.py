import boto3
import logging
from botocore.exceptions import NoCredentialsError
import os
from dotenv import load_dotenv

load_dotenv()

# Configure AWS Credentials
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")


def upload_video_to_s3(video_file_path, s3_key):
    """
    Uploads a video file to an S3 bucket using upload_fileobj.

    :param video_file_path: Path to the video file on disk.
    :param s3_key: S3 key (path in S3 where the video will be stored).
    """
    try:
        # Create an S3 client
        s3 = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY
        )

        # Open the video file in binary mode
        with open(video_file_path, "rb") as video_file:
            s3.put_object(
                video_file,
                BUCKET_NAME,
                s3_key,
                ContentType='video/mp4',  # Explicitly set Content-Type
                ExtraArgs={'ContentType': 'video/mp4'},  # Explicitly set Content-Type
                ContentDisposition='inline'  # Display the video in the browser
            )

        logging.info(f"Upload successful: {video_file_path} → s3://{BUCKET_NAME}/{s3_key}")
        return f"https://{BUCKET_NAME}.s3.amazonaws.com/{s3_key}"

    except Exception as e:
        logging.error(f"Failed to upload {video_file_path} to S3: {e}")
        return None

# Example Usage
video_path = "/home/qu-user1/Github/QuCreate-airflow/output/6797a8994202d613823b6c5a/video.mp4"
s3_video_key = "temp/uploaded_video.mp4"  # The S3 key

s3_url = upload_video_to_s3(video_path, s3_video_key)
print(f"Uploaded video URL: {s3_url}")