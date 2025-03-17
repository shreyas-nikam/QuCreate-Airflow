import logging
import requests
import base64
import os
from dotenv import load_dotenv
import nacl.encoding
import nacl.public

# Load environment variables from a .env file
load_dotenv()

# GitHub API URL and Token
GITHUB_API_URL = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")  


def get_repo_public_key(owner, repo, token):
    """
    Retrieve the public key (and key_id) for a given GitHub repository
    so we can encrypt secrets for GitHub Actions.
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/secrets/public-key"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}",
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data["key"], data["key_id"]


def encrypt_secret(public_key: str, secret_value: str) -> str:
    """
    Encrypt a plaintext secret using the repository's public key (Base64).
    GitHub requires libsodium sealed box encryption.
    """
    public_key_bytes = base64.b64decode(public_key)
    sealed_box = nacl.public.SealedBox(nacl.public.PublicKey(public_key_bytes))
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def put_secret(owner, repo, token, secret_name, encrypted_value, key_id):
    """
    Create or update a GitHub Actions secret in the specified repo.
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/secrets/{secret_name}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "encrypted_value": encrypted_value,
        "key_id": key_id
    }
    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code in [201, 204]:
        print(f"Secret {secret_name} created/updated successfully.")
    else:
        print(f"Failed to create/update secret {secret_name}: {resp.text}")
        resp.raise_for_status()


def create_or_update_file(owner, repo, token, file_path, file_content, commit_message, branch="main"):
    """
    Create or update a file in the given repo using the GitHub Content API.
    file_path is something like '.github/workflows/my-workflow.yml'.
    file_content is a string (the file contents).
    """
    # 1. Check if file exists (to get its current sha). If it doesn't exist, we'll create it.
    get_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{file_path}?ref={branch}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}",
    }
    get_resp = requests.get(get_url, headers=headers)

    if get_resp.status_code == 200:
        # File exists; get its SHA
        file_sha = get_resp.json()["sha"]
    elif get_resp.status_code == 404:
        # File doesn't exist
        file_sha = None
    else:
        get_resp.raise_for_status()

    # 2. Create or update the file
    put_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{file_path}"
    payload = {
        "message": commit_message,
        "content": base64.b64encode(file_content.encode("utf-8")).decode("utf-8"),
        "branch": branch
    }
    if file_sha:
        payload["sha"] = file_sha  # required to update an existing file

    put_resp = requests.put(put_url, headers=headers, json=payload)
    if put_resp.status_code in [200, 201]:
        print(f"File '{file_path}' created/updated successfully in branch '{branch}'.")
    else:
        print(f"Failed to create/update file '{file_path}': {put_resp.text}")
        put_resp.raise_for_status()


def create_tag(owner, repo, token, tag_name, commit_sha, tag_message=None):
    """
    Create (push) a lightweight Git tag referencing an existing commit.
    This will create a new ref named 'refs/tags/{tag_name}' pointing to commit_sha.
    
    For an *annotated* tag, you could:
      1) create a tag object via POST /repos/{owner}/{repo}/git/tags
      2) then create a reference to that object
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}",
    }
    data = {
        "ref": f"refs/tags/{tag_name}",
        "sha": commit_sha
    }
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code == 201:
        print(f"Tag '{tag_name}' created successfully.")
    else:
        print(f"Failed to create tag '{tag_name}': {resp.text}")
        resp.raise_for_status()



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
