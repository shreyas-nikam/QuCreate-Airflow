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
from course.helper import get_slides, get_module_information

def fetch_outline(course_id, module_id):
    try:
        mongodb_client = AtlasClient()

        # Get the course_design object
        course = mongodb_client.find("course_design", filter={"_id": ObjectId(course_id)})
        if not course:
            return "Course not found"

        course = course[0]
        module = next((m for m in course.get("modules", []) if m.get("module_id") == ObjectId(module_id)), None)
        if not module:
            return "Module not found"

        return module.get("outline")
    
    except Exception as e:
        logging.error(f"Error in getting course and module: {e}")

def _get_course_and_module(course_id, module_id):
    try:
        mongodb_client = AtlasClient()

        # Get the course_design object
        course = mongodb_client.find("course_design", filter={"_id": ObjectId(course_id)})
        if not course:
            return "Course not found", None

        course = course[0]
        module = next((m for m in course.get("modules", []) if m.get("module_id") == ObjectId(module_id)), None)
        if not module:
            return None, "Module not found"

        return course, module
    except Exception as e:
        logging.error(f"Error in getting course and module: {e}")
        return None, None

def generate_content(entry_id):
    mongodb_client = AtlasClient()
    entry = mongodb_client.find("in_content_generation_queue", filter={"_id": ObjectId(entry_id)})
    course_id = entry[0].get("course_id")
    module_id = entry[0].get("module_id")

    outline = fetch_outline(course_id, module_id)

    if outline == "Course not found" or outline == "Module not found":
        return outline
    
    slides = get_slides(module_id, outline)

    with open(f"output/{module_id}/slides.json", "w") as f:
        f.write(slides)
    
    # upload it to s3
    key = f"qu-course-design/{course_id}/{module_id}/pre_processed_content/slides.json"
    s3_client = S3FileManager()

    s3_client.upload_file(f"output/{module_id}/slides.json", key)

    slide_resource = {
        "resource_type": "Slide_Content",
        "resource_name": "Slide Content",
        "resource_description": "Slide content generated using AI",
        "resource_link": "https://qucoursify.s3.us-east-1.amazonaws.com/"+key,
        "resource_id": ObjectId()
    }

    mongodb_client = AtlasClient()
    course, module = _get_course_and_module(course_id, module_id)

    if not course or not module:
        return "Course or Module not found"
    
    module["pre_processed_content"].append(slide_resource)
    

    with open(f"output/{module_id}/module_info.md", "w") as f:
        f.write(get_module_information(outline))

    key = f"qu-course-design/{course_id}/{module_id}/pre_processed_content/module_info.md"
    s3_client.upload_file(f"output/{module_id}/module_info.md", key)

    module_info_resource = {
        "resource_type": "Module_Information",
        "resource_name": "Module Information",
        "resource_description": "Module Information generated using AI",
        "resource_link": "https://qucoursify.s3.us-east-1.amazonaws.com/"+key,
        "resource_id": ObjectId()
    }

    module["pre_processed_content"].append(module_info_resource)

    course["modules"] = [module if m.get("module_id") == ObjectId(module_id) else m for m in course.get("modules", [])]

    mongodb_client.update("course_design", filter={"_id": ObjectId(course_id)}, update=course)

    return "Content generated successfully"








