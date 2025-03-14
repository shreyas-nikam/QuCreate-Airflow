"""
Content Consists of:
1. Slide_Content: json of slides with the following fields:
    - slide_header
    - slide_content
    - speaker_notes
2. Note: Markdown content for Module Information
"""


"""
Steps for generating the content:
1. Fetch the outline from mongodb.
2. Generate the content for the slides and module information.
3. Write the content to a file and the module information as well.
4. Upload the file to s3.
5. Update the mongodb link with the link.
"""




from utils.mongodb_client import AtlasClient
from utils.s3_file_manager import S3FileManager
from bson.objectid import ObjectId
import logging
from utils.s3_file_manager import S3FileManager
from pathlib import Path
import os
def fetch_outline(course_id, module_id):
    try:
        mongodb_client = AtlasClient()

        # Get the course_design object
        course = mongodb_client.find("course_design", filter={
                                     "_id": ObjectId(course_id)})
        if not course:
            return "Course not found"

        course = course[0]
        module = next((m for m in course.get("modules", []) if m.get("module_id") == ObjectId(module_id)), None)
        if not module:
            return "Module not found"

        outline_link = module.get("pre_processed_outline")[0]["resource_link"]

        s3_file_manager = S3FileManager()
        download_path = f"output/{module_id}/outline.md"

        if Path(download_path).exists():
            os.remove(download_path)

        Path(download_path[:download_path.rindex("/")]).mkdir(parents=True, exist_ok=True)
        outline_key = outline_link.split("amazonaws.com/")[1]
        s3_file_manager.download_file(outline_key, download_path)

        # read outline
        with open(download_path, "r") as f:
            outline_content = f.read()

        return outline_content

    except Exception as e:
        logging.error(f"Error in fetching outline: {e}")



def _get_course_and_module(course_id, module_id):
    try:
        mongodb_client = AtlasClient()

        # Get the course_design object
        course = mongodb_client.find("course_design", filter={
                                     "_id": ObjectId(course_id)})
        if not course:
            return "Course not found", None

        course = course[0]
        module = next((m for m in course.get("modules", []) if m.get(
            "module_id") == ObjectId(module_id)), None)
        if not module:
            return None, "Module not found"

        return course, module
    except Exception as e:
        logging.error(f"Error in getting course and module: {e}")
        return None, None
