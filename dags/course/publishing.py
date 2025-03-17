"""
Publishing artifacts consist of:
1. Slide_Generated
2. Video
3. Assessment
4. Chatbot
5. Quiz Certificate -> temporary needs to be created
6. Home Page Introduction
7. App image
8. Artifacts Linked
9. slides_links
10. video_links
11. Module Names
12. Module Introductions


1. How to display additional artifacts like the labs, podcasts and the writing resources?
2. iterative addition and publishing
"""


"""
# Only courses will be able to be published
1. Get the course if it is already published
2. Get the modules ready for publishing from the queue. Do not delete them from the queue. 
3. Get the artifacts for publishing the modules.
4. append the artifacts to the appropriate fields
5. update Mongodb with the changes.
"""

import asyncio
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont
from langchain.prompts.prompt import PromptTemplate
from utils.converter import _convert_object_ids_to_strings
from utils.mongodb_client import AtlasClient
from bson import ObjectId
import logging
from textwrap import wrap
import os
from utils.s3_file_manager import S3FileManager
from utils.retriever import Retriever
from utils.llm import LLM

course_object = {
    "app_name": "",
    "course_id": "",
    "app_code": "",
    "app_image_location": "",
    "home_page_introduction": "",
    "short_description": "",
    "document_link": "",
    "certificate_path": "",
    "slides_links": [],
    "course_names_videos": [],
    "course_module_information": [],
    "course_names_slides": [],
    "videos_links": [],
    "module_ids": [],
    "has_chatbot": False,
    "has_quiz": False,
    "external_link": "",
    "contact_form_link": "",
    "disclaimer": "\nThis course contains content that has been partially or fully generated using artificial intelligence (AI) technology. While every effort has been made to ensure the accuracy and quality of the materials, please note that AI-generated content may not always reflect the latest developments, best practices, or personalized nuances within the field. We encourage you to critically evaluate the information presented and consult additional resources where necessary.\n"
}

mongo_client_test = AtlasClient(dbname="test")
mongo_client_env = AtlasClient()

async def _convert_to_pdf(course_id, module_id, slide_link):
    # Steps:
    # 1. Download the slide in a temp location
    # 2. Convert the slide to pdf
    # 3. Upload the pdf to s3
    # 4. Return the link to the pdf
    s3_file_manager = S3FileManager()
    slide_key = slide_link.split("amazonaws.com/")[1]
    with open(f"output/{module_id}/slide.pptx", "wb") as file:
        slide = s3_file_manager.get_object(slide_key)
        file.write(slide["Body"].read())
    Path(f"output/{module_id}").mkdir(parents=True, exist_ok=True)
    os.system(f"libreoffice --headless --convert-to pdf --outdir output/{module_id}/ output/{module_id}/slide.pptx")

    pdf_key = f"qu-course-design/{course_id}/{module_id}/post_processed_deliverables/slides.pdf"
    await s3_file_manager.upload_file(f"output/{module_id}/slide.pdf", pdf_key, "application/pdf")

    return f"https://qucoursify.s3.us-east-1.amazonaws.com/{pdf_key}"

async def _process_resource(course_id, module_id, resource, s3_file_manager):
    """
    Process a single resource from a module and return its processed data
    
    Args:
        course_id (str): The ID of the course
        module_id (str): The ID of the module
        resource (dict): Resource object containing type and link
        s3_file_manager (S3FileManager): S3 file manager instance
    
    Returns:
        tuple: Processed data based on resource type
    """
    resource_type = resource['resource_type']
    resource_link = resource['resource_link']

    if resource_type == "Slide_Generated":
        return await _convert_to_pdf(course_id, module_id, resource_link), None
    
    elif resource_type == "Video":
        return resource_link, None
    
    elif resource_type == "Note":
        notes_key = resource_link.split("amazonaws.com/")[1]
        notes_obj = s3_file_manager.get_object(notes_key)
        return notes_obj["Body"].read().decode("utf-8"), None
    
    elif resource_type == "Assessment":
        assessment_key = resource_link.split("amazonaws.com/")[1]
        assessment_obj = s3_file_manager.get_object(assessment_key)
        assessment = json.loads(assessment_obj["Body"].read().decode("utf-8"))
        return None, assessment
    
    elif resource_type == "Chatbot" and resource_link:
        chatbot_key = resource_link.split("amazonaws.com/")[1]
        chatbot_obj = s3_file_manager.get_object(chatbot_key)
        return chatbot_obj["Body"].read().decode("utf-8"), None
    
    return None, None

async def _setup_chatbot(course_id, chatbot_text, s3_file_manager):
    """
    Set up chatbot by creating and uploading vector store
    
    Args:
        course_id (str): The ID of the course
        chatbot_text (str): Text content for chatbot
        s3_file_manager (S3FileManager): S3 file manager instance
    
    Returns:
        str: Chatbot link
    """
    retriever = Retriever()
    output_path = f"output/{course_id}/retriever"
    Path(output_path).mkdir(parents=True, exist_ok=True)
    retriever.create_vector_store(chatbot_text, output_path)

    files = [
        "bm25_retriever.pkl",
        "faiss_retriever.pkl",
        "hybrid_db/index.pkl",
        "hybrid_db/index.faiss"
    ]
    
    for file in files:
        local_path = f"{output_path}/{file}"
        s3_key = f"qu-course-design/{course_id}/retriever/{file}"
        await s3_file_manager.upload_file(local_path, s3_key)
    
    return f"https://qucoursify.s3.us-east-1.amazonaws.com/qu-course-design/{course_id}/retriever"

async def _setup_quiz(course_id, questions):
    """
    Set up quiz by creating and uploading questions file
    
    Args:
        course_id (str): The ID of the course
        questions (dict): Quiz questions
    
    Returns:
        str: Questions file URL
    """
    quiz_path = f"output/{course_id}/quiz"
    Path(quiz_path).mkdir(parents=True, exist_ok=True)
    quiz_file_path = f"{quiz_path}/quiz.json"
    
    with open(quiz_file_path, "w") as quiz_file:
        json.dump(questions, quiz_file)
    
    key = f"qu-course-design/{course_id}/quiz.json"
    s3_client = S3FileManager()
    await s3_client.upload_file(quiz_file_path, key)
    return f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

async def _update_modules(course_id, course):
    """
    Update course modules with processed resources and create necessary artifacts
    
    Args:
        course_id (str): The ID of the course
        course (dict): Course object to be updated
    
    Returns:
        dict: Updated course object
    """
    logging.info(f"Updating modules for course: {course_id}")
    
    course_design = mongo_client_env.find("course_design", filter={"_id": ObjectId(course_id)})[0]
    module_objs = mongo_client_env.find("post_processed_deliverables", filter={"course_id": course_id})
    
    if not module_objs:
        raise Exception("No modules found for the course")

    module_ids = set([module["module_id"] for module in module_objs])
    modules = [module for module in course_design['modules'] if str(module['module_id']) in module_ids]

    if not modules:
        raise Exception("No modules found for the course")

    slide_links, slide_names, video_links = [], [], []
    module_ids, course_module_information = [], []
    questions = {}
    chatbot_text_complete = ""
    s3_file_manager = S3FileManager()
    atlas_client = AtlasClient()

    # Process each module
    for module in modules:
        module_id = module["module_id"]
        module_ids.append(module_id)
        slide_names.append(module["module_name"])
        module['status'] = "Published"

        for resource in module['pre_processed_deliverables']:
            result, assessment = await _process_resource(course_id, module_id, resource, s3_file_manager)
            
            if resource['resource_type'] == "Slide_Generated" and result:
                slide_links.append(result)
            elif resource['resource_type'] == "Video" and result:
                video_links.append(result)
            elif resource['resource_type'] == "Note" and result:
                course_module_information.append(result)
            elif resource['resource_type'] == "Assessment" and assessment:
                questions[module["module_name"]] = assessment
            elif resource['resource_type'] == "Chatbot" and result:
                course["has_chatbot"] = True
                chatbot_text_complete += result
    
        if module['selected_labs']:
            for lab_index, lab in enumerate(module['selected_labs']):
                lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab)})[0]
                if lab['status']=='Review':
                    lab['status'] = 'Published'
                    atlas_client.update("lab_design", filter={"_id": ObjectId(lab['_id'])}, update={"$set": lab})
                    if len(module['selected_labs'])>1:
                        course_module_information[-1]+=f"\n\n### Lab {lab_index}:\n"
                    if lab['lab_url']:
                        course_module_information[-1]+="\n\n### Demo:\n"
                        course_module_information[-1]+=f"[![Run on QuSandbox](https://qucoursify.s3.us-east-1.amazonaws.com/qu-skillbridge/qusandbox_button.png)]({lab['lab_url']})\n"
                    if lab['documentation_url']:
                        course_module_information[-1]+="\n\n### Documentation:\n"
                        course_module_information[-1]+=f"[![image](https://qucoursify.s3.us-east-1.amazonaws.com/qu-lab-design/images/codelabs.png)]({lab['documentation_url']})\n"

    # Setup chatbot if needed
    if course["has_chatbot"]:
        course["chatbot_link"] = await _setup_chatbot(course_id, chatbot_text_complete, s3_file_manager)
        course["has_chatbot"] = False

    # Setup quiz if needed
    if questions:
        course['has_quiz'] = True
        course["questions_file"] = await _setup_quiz(course_id, questions)

    # Update course object
    course.update({
        "slides_links": slide_links,
        "course_names_slides": slide_names,
        "videos_links": video_links,
        "module_ids": module_ids,
        "course_module_information": course_module_information,
        "course_names_videos": slide_names
    })

    # Update course design status
    for module in course_design['modules']:
        if str(module['module_id']) in module_ids:
            module['status'] = "Published"
    
    course_design['status'] = "Published"
    mongo_client_env.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": course_design})

    return course


def _create_certificate(course_id, course_name):
    certificate = Image.open(
        open("dags/course/assets/QU-Certificate.jpg", "rb"))

    # Create an ImageDraw object to write on the image
    draw = ImageDraw.Draw(certificate)

    # Font settings (bold fonts)
    # Replace with the path to a valid bold .ttf font file
    font_path_bold = "dags/course/assets/ArialBold.ttf"
    font_size_title = 40  # Font size for the title
    font_size_message = 20  # Font size for the message
    font_title = ImageFont.truetype(font_path_bold, font_size_title)
    font_message = ImageFont.truetype(font_path_bold, font_size_message)

    # Text to be added to the certificate
    title_text = course_name
    message_text = f"is hereby recognized to have completed QuantUniversity's {course_name} Course."

    # Wrapping helper function
    def draw_wrapped_text(draw, text, font, position, max_width, fill, align="left", line_spacing=10):
        """Draw wrapped text with specified alignment."""
        lines = []
        for line in text.split("\n"):  # Preserve existing line breaks
            lines.extend(wrap(line, width=max_width // font.getbbox("A")[2]))

        y_offset = 0
        for line in lines:
            line_width = font.getbbox(line)[2]
            if align == "center":
                # Center-align horizontally
                x_start = position[0] - line_width // 2
            elif align == "left":
                x_start = position[0]  # Left-aligned
            else:
                x_start = position[0] - line_width  # Right-aligned
            draw.text((x_start, position[1] + y_offset),
                      line, font=font, fill=fill)
            y_offset += font.getbbox(line)[3] - \
                font.getbbox(line)[1] + line_spacing

    # Certificate dimensions
    image_width, image_height = certificate.size

    # Title text position and wrapping
    title_position = (image_width // 2, 180)  # Centered horizontally
    max_width_title = certificate.size[0] + 200  # Leave some margin
    draw_wrapped_text(draw, title_text, font_title, title_position,
                      max_width_title, (255, 255, 255), align="center", line_spacing=15)

    # Message text position and wrapping
    text_position_date = (50, 420)  # Left-aligned with a margin
    max_width_message = certificate.size[0] + 200  # Leave some margin
    draw_wrapped_text(draw, message_text, font_message, text_position_date,
                      max_width_message, (0, 0, 0), align="left", line_spacing=10)

    # Save the modified image
    output_path = f'output/{course_id}/quiz_certificate.jpg'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    certificate.save(output_path)

    key = f"qu-course-design/{course_id}/quiz_certificate.jpg"
    s3_client = S3FileManager()
    asyncio.run(s3_client.upload_file(output_path, key))

    return "https://qucoursify.s3.us-east-1.amazonaws.com/" + key



def generate_short_description(course):
    llm = LLM()
    prompt = "Generate a short description for the course. It should be only two lines long. Do not return anything else Here's the name and description of the course:\n\nCourse Name: {{course_name}}\n\nCourse Description: {{course_description}}"
    inputs = {
        "course_name": course["app_name"],
        "course_description": course["home_page_introduction"],
        "modules": _convert_object_ids_to_strings(course["modules"])
    }
    prompt = PromptTemplate(template=prompt, inputs=inputs)
    return llm.get_response(prompt, inputs)

def generate_course_description(course):
    llm = LLM()
    prompt = "Generate a course description for the course. It should be in markdown format. Do not return anything else Here's the name and description of the course:\n\nCourse Name: {{course_name}}\n\nCourse Description: {{course_description}}"
    inputs = {
        "course_name": course["app_name"],
        "course_description": course["home_page_introduction"],
        "modules": _convert_object_ids_to_strings(course["modules"])
    }
    prompt = PromptTemplate(template=prompt, inputs=inputs)
    return llm.get_response(prompt, inputs)

def handle_update_course(course_id):
    """
    Steps:
    1. Get the course object from courses
    2. Get the course design from the courses_design.
    3. Get the modules ready for publishing from the publishing queue.
    4. For all the modules in the publishing queue, update the course objects.
    5. Update the course object in the courses collection.
    6. Update the course design with the status for the published courses in the course_design collection.
    """
    try:
        course_design = mongo_client_env.find("course_design", filter={"_id": ObjectId(course_id)})[0]
        
        course = mongo_client_test.find("courses", filter={"course_id": ObjectId(course_id)})

        course = course[0]
        certificate_path = _create_certificate(course_id, course_design["course_name"])

        course["certificate_path"] = certificate_path
        
        course['app_name'] = course_design["course_name"]
        course["app_image_location"] = course_design["course_image"]
        course["home_page_introduction"] = course_design["course_outline"]

        course = asyncio.run(_update_modules(course_id, course))
        course["short_description"] = generate_short_description(course)
        course["home_page_introduction"] = generate_course_description(course)

        mongo_client_test.update("courses", filter={"course_id": ObjectId(course_id)}, update={"$set": course})

        return True

    except Exception as e:
        logging.error(f"Error in updating course: {e}")


def handle_create_course(course_id):
    """
    Steps: 
    Create a new course object
    Get the course from the course design
    Get the modules ready for publishing from the publishing queue
    For all the modules in the publishing queue, update the course objects
    Insert the course object in the courses collection
    Update the course design with the status for the published courses in the course_design collection
    """
    try:
        logging.info(f"Creating course: {course_id}")

        course = course_object

        print(course)
        course["course_id"] = ObjectId(course_id)

        course_design = mongo_client_env.find("course_design", filter={"_id": ObjectId(course_id)})[0]

        logging.info("Creating certificate")

        certificate_path = _create_certificate(course_id, course_design["course_name"])

        course["certificate_path"] = certificate_path

        if not course_design:
            return "Course design not found"

        course['app_name'] = course_design["course_name"]
        course["app_image_location"] = course_design["course_image"]
        course["home_page_introduction"] = course_design["course_outline"]

        logging.info("Updating modules")
        course = asyncio.run(_update_modules(course_id, course))
        course["short_description"] = generate_short_description(course)
        course["home_page_introduction"] = generate_course_description(course)

        mongo_client_test.insert("courses", course)

        return True

    except Exception as e:
        logging.error(f"Error in creating course: {e}")
