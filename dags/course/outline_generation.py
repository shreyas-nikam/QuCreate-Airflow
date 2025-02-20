"""
This will take the artifacts and generate the outline using assistants api.
The outline will consist of the number of slides, etc for generating the actual content.

"""

"""
Steps:
1. Fetch all the artifacts.
2. Feed it as files to the assistants api.
3. Get the outline.
4. Upload the outline on the mongodb.
"""




from utils.s3_file_manager import S3FileManager
from utils.mongodb_client import AtlasClient
import logging
from bson.objectid import ObjectId
from course.helper import generate_outline
from pathlib import Path
import asyncio
def _get_course_and_module(course_id, module_id):
    """
    Get the course and module object from the course_id and module_id
    """
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


def fetch_artifacts(course_id, module_id):
    try:
        course, module = _get_course_and_module(course_id, module_id)

        if not course or not module:
            logging.error("Course or module not found")
            return None

        output_path = f"output/{module_id}/files"
        Path(output_path).mkdir(parents=True, exist_ok=True)
        for resource in module['raw_resources']:
            # Fetch the resources from s3
            s3 = S3FileManager()
            resource_key = resource['resource_link'].split(
                "/")[3] + "/" + "/".join(resource['resource_link'].split("/")[4:])
            if resource['resource_type'] == "File":
                logging.info(f"Downloading file: {resource_key}")
                s3.download_file(resource_key, f"{
                                 output_path}/{resource['resource_link'].split('/')[-1]}")

            # TODO: Add support for other resource types like images, links and notes etc.

        return output_path

    except Exception as e:
        logging.error(f"Error in fetching artifacts: {e}")


def upload_outline(course_id, module_id, outline):
    try:
        mongodb_client = AtlasClient()

        course, module = _get_course_and_module(course_id, module_id)

        # write the outline to a outline.md file, upload it to s3, add the resource to the pre_processed_outline object for the module and update it in mongodb
        outline_path = f"output/{module_id}/outline.md"
        with open(outline_path, "w") as f:
            f.write(outline)

        s3 = S3FileManager()
        key = "qu-course-design/" + course_id + "/modules/" + \
            module_id + "/pre_processed_outline/outline.md"
        asyncio.run(s3.upload_file(outline_path, key))
        resource_link = "https://qucoursify.s3.us-east-1.amazonaws.com/" + key
        resource = {
            "resource_type": "Note",
            "resource_link": resource_link,
            "resource_name": "Outline",
            "resource_description": "Outline for the module",
            "resource_id": ObjectId()
        }

        # Upload the outline on the mongodb.

        # Add the resource to the pre_processed_outline object for the module if it exists, if it doesnt exist, create it.
        module["pre_processed_outline"] = []
        module["pre_processed_outline"].append(resource)
        module["status"] = "Outline Review"
        course["modules"] = [m if m.get("module_id") != ObjectId(
            module_id) else module for m in course["modules"]]

        mongodb_client.update("course_design", filter={"_id": ObjectId(
            course_id)}, update={"$set": {"modules": course["modules"]}})
        logging.info("Outline uploaded")

    except Exception as e:
        logging.error(f"Error in uploading outline: {e}")


async def process_outline(entry_id):
    logging.info(f"Processing entry with ID: {
                 entry_id} for outline generation.")
    mongodb_client = AtlasClient()
    entry = mongodb_client.find("in_outline_generation_queue", filter={
                                "_id": ObjectId(entry_id)})
    if not entry:
        return "Entry not found"

    entry = entry[0]
    course_id = entry.get("course_id")
    module_id = entry.get("module_id")
    instructions = entry.get("instructions")

    logging.info(f"Fetched entry from the queue. Course ID: {course_id}, Module ID: {module_id}")
    logging.info(f"Instructions: {instructions}")

    logging.info("Fetching artifacts")
    # Fetch all the artifacts.
    artifacts_path = fetch_artifacts(course_id, module_id)
    logging.info(f"Artifacts fetched at: {artifacts_path}")
    # Feed it as files to the assistants api.
    # artifacts_path is output/module_id
    logging.info("Generating outline")
    outline = await generate_outline(artifacts_path, module_id, instructions)
    logging.info(f"Outline generated: {outline}")
    # Upload the outline on the mongodb.
    logging.info("Uploading outline")
    upload_outline(course_id, module_id, outline)
    logging.info("Outline uploaded")

    return True
