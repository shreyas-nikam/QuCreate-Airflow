import logging
import requests
import base64
import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# GitHub API URL and Token
GITHUB_API_URL = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")  



gitignore_content = """
# Python
*.pyc
__pycache__/

# Streamlit
.streamlit/
"""


requirements_content = """
streamlit==1.24.0
"""

template_streamlit_app = """
import streamlit as st

st.set_page_config(page_title="QuCreate Streamlit Lab", layout="wide")
st.sidebar.image("assets/images/company_logo.jpg")
st.sidebar.divider()
st.title("QuCreate Streamlit Lab")
st.divider()

# Code goes here

st.divider()
st.write("© 2025 QuantUniversity. All Rights Reserved.")
st.caption("The purpose of this demonstration is solely for educational use and illustration. "
           "To access the full legal documentation, please visit this link. Any reproduction of this demonstration "
           "requires prior written consent from QuantUniversity.")
"""

readme_content = """
# QuCreate Streamlit Lab

This repository contains a Streamlit application for demonstrating the features and capabilities of the QuCreate platform.

## Features
- Streamlit sidebar with a company logo.
- Template for easy development.
- Placeholder for adding custom code.

## Getting Started

### Prerequisites
- Python 3.8 or later
- Streamlit installed (see `requirements.txt`).

### Installation
1. Clone the repository
2. Install dependencies:
`pip install -r requirements.txt`

### Running the Application
1. Run the Streamlit app:

### Development
1. Modify the `app.py` file to add your custom code.
2. Use the placeholder section (`# Code goes here`) to add new functionality.

### Deployment
- Deploy your Streamlit app using Streamlit Sharing, Docker, or any other platform supporting Python web applications.

## License
© 2025 QuantUniversity. All Rights Reserved. Educational use only. For licensing details, please contact QuantUniversity.
"""




def _create_github_repo(repo_name, description="", private=False):
    """Create a new GitHub repository."""
    url = f"{GITHUB_API_URL}/user/repos"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {
        "name": repo_name,
        "description": description,
        "private": private,
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        logging.info(f"Repository '{repo_name}' created successfully!")
        return response.json()["html_url"]
    else:
        logging.info(f"Failed to create repository: {response.status_code}, {response.text}")
        return None


def upload_file_to_github(repo_name, file_path, file_content, commit_message="Add file"):
    """Upload a file to a GitHub repository."""
    url = f"{GITHUB_API_URL}/repos/{GITHUB_USERNAME}/{repo_name}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {
        "message": commit_message,
        "content": base64.b64encode(file_content.encode("utf-8")).decode("utf-8"),
    }
    response = requests.put(url, headers=headers, json=data)
    if response.status_code == 201:
        logging.info(f"File '{file_path}' uploaded successfully!")
        return response.json()
    else:
        logging.info(f"Failed to upload file: {response.status_code}, {response.text}")
        return None


def create_github_issue(repo_name, issue_title, issue_body="", labels=None):
    """
    Create an issue in a GitHub repository.
    
    :param repo_name: Name of the repository
    :param issue_title: Title of the issue
    :param issue_body: Description or body of the issue
    :param labels: List of labels for the issue (optional)
    """
    url = f"{GITHUB_API_URL}/repos/{GITHUB_USERNAME}/{repo_name}/issues"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {
        "title": issue_title,
        "body": issue_body,
        "labels": labels or [],
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        logging.info(f"Issue '{issue_title}' created successfully!")
        return response.json()
    else:
        logging.info(f"Failed to create issue: {response.status_code}, {response.text}")
        return None


def get_file_sha(repo_name, file_path):
    """Get the SHA of the existing file in the repository."""
    url = f"{GITHUB_API_URL}/repos/{GITHUB_USERNAME}/{repo_name}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["sha"]
    else:
        logging.info(f"Failed to fetch file SHA: {response.status_code}, {response.text}")
        return None

def update_file_in_github(repo_name, file_path, new_content, commit_message="Update file"):
    """Update an existing file in the GitHub repository."""
    sha = get_file_sha(repo_name, file_path)
    if not sha:
        logging.info(f"Cannot update file: Unable to fetch SHA for {file_path}")
        return

    url = f"{GITHUB_API_URL}/repos/{GITHUB_USERNAME}/{repo_name}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {
        "message": commit_message,
        "content": base64.b64encode(new_content.encode("utf-8")).decode("utf-8"),
        "sha": sha,  # Provide the SHA of the existing file
    }
    response = requests.put(url, headers=headers, json=data)
    if response.status_code == 200:
        logging.info(f"File '{file_path}' updated successfully!")
    else:
        logging.info(f"Failed to update file '{file_path}': {response.status_code}, {response.text}")


def create_repo_in_github(repo_name, description, private=False):
    """Create a new GitHub repository for a Streamlit lab."""
    repo_url = _create_github_repo(repo_name, description, private)

    if repo_url:
        upload_file_to_github(repo_name, ".gitignore", gitignore_content, "Add .gitignore")
        upload_file_to_github(repo_name, "requirements.txt", requirements_content, "Add requirements.txt")
        upload_file_to_github(repo_name, "app.py", template_streamlit_app, "Add template Streamlit application")
        upload_file_to_github(repo_name, "README.md", readme_content, "Add README")

    else:
        return "Failed to create repository."


# # Example usage

# for creating lab
# create_lab_in_github("streamlit-lab", "Streamlit Lab for QuCreate", private=False)
# Create it as an object id and store the unique object

# for uploading the business requirements and technical requirements
# upload_file_to_github("streamlit-lab", "business_requirements.md", business_requirements_content, "Add business requirements")

# for updating the business requirements and technical requirements on user's changes (keep the latest version)
# update_file_in_github("streamlit-lab", file_path, new_content, "Update README with new instructions")

# for adding issues to the repository. This data should come from a form in hte frontend.
# create_github_issue("streamlit-lab", "Issue Title", "Issue Description", ["bug", "enhancement"])
