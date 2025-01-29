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
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont
from utils.mongodb_client import AtlasClient
from bson import ObjectId
import logging
from textwrap import wrap
import os
from utils.s3_file_manager import S3FileManager
from utils.retriever import Retriever

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


async def _update_modules(course_id, course):
    logging.info(f"Updating modules for course: {course_id}")
    mongo_client = AtlasClient()
    course_design = mongo_client.find("course_design", filter={"_id": ObjectId(course_id)})[0]
    module_objs = mongo_client.find("post_processed_deliverables", filter={"course_id": ObjectId(course_id)})

    if len(module_objs) == 0:
        raise Exception("No modules found for the course")
    
    module_ids = set([module["module_id"] for module in module_objs])

    modules = []
    for module in course_design['modules']:
        if module['module_id'] in module_ids:
            modules.append(module)
    
    if len(modules) == 0:
        raise Exception("No modules found for the course")

    slide_links = []
    slide_names = []
    video_links = []
    module_ids = []
    questions = []
    course_module_information = []
    s3_file_manager = S3FileManager()
    chatbot_text_complete = ""

    for module in modules:
        logging.info(f"Updating module: {module['module_id']}")
        module_id = module["module_id"]
        module_ids.append(module_id)
        
        slide_names.append(module["module_name"])
        module['status'] = "Published"
        for resource in module['pre_processed_deliverables']:
            if resource['resource_type'] == "Slide_Generated":
                slide_link = resource['resource_link']
                slide_links.append(slide_link)
            elif resource['resource_type'] == "Video":
                video_link = resource['resource_link']
                video_links.append(
                    f"""
                    <div style='padding:56.25% 0 0 0;position:relative;'><iframe src='{video_link}?badge=0&amp;autopause=0&amp;player_id=0&amp;app_id=58479' frameborder='0' allow='autoplay; fullscreen; picture-in-picture; clipboard-write' style='position:absolute;top:0;left:0;width:100%;height:100%;' title='{module_obj["module_name"]}'></iframe></div><script src='https://player.vimeo.com/api/player.js'></script>
                    """
                )
            elif resource['resource_type'] == "Note":
                notes_link = resource['resource_link']
                notes_key = notes_link.split("amazonaws.com/")[1]
                notes_obj = s3_file_manager.get_object(notes_key)
                notes = notes_obj["Body"].read().decode("utf-8")
                course_module_information.append(notes)
            elif resource['resource_type'] == "Assessment":
                assessment_link = resource['resource_link']
                assessment_key = assessment_link.split("amazonaws.com/")[1]
                assessment_obj = s3_file_manager.get_object(assessment_key)
                assessment = assessment_obj["Body"].read().decode("utf-8")
                questions.append(assessment)
            elif resource['resource_type'] == "Chatbot":
                course["has_chatbot"] = True
                chabot_link = resource['resource_link']
                chatbot_key = chabot_link.split("amazonaws.com/")[1]
                chatbot_obj = s3_file_manager.get_object(chatbot_key)
                chatbot_text = chatbot_obj["Body"].read().decode("utf-8")
                chatbot_text_complete += chatbot_text
    
    if course["has_chatbot"]:
        logging.info("Creating chatbot")
        retriever = Retriever()
        Path(f"output/{course_id}/retriever").mkdir(parents=True, exist_ok=True)
        retriever.create_vector_store(chatbot_text_complete, f"output/{course_id}/retriever")
        # Upload chatbot to s3
        files = [f"output/{course_id}/retriever/bm25_retriever.pkl", f"output/{course_id}/retriever/faiss_retriever.pkl", f"output/{course_id}/retriever/hybrid_db/index.pkl", f"output/{course_id}/retriever/hybrid_db/index.faiss"]
        file_keys = ["retriever/bm25_retriever.pkl", "retriever/faiss_retriever.pkl", "retriever/hybrid_db/index.pkl", "retriever/hybrid_db/index.faiss"]
        for file, key in zip(files, file_keys):
            await s3_file_manager.upload_file(file, f"qu-course-design/{course_id}/{key}")
        chabot_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/qu-course-design/{course_id}/retriever"
        course["chatbot_link"] = chabot_link
    

    if len(questions) > 0:
        logging.info("Creating quiz")
        course['has_quiz'] = True
        Path(f"output/{course_id}/quiz").mkdir(parents=True, exist_ok=True)
        quiz_file = open(f"output/{course_id}/quiz/quiz.json", "w")
        json.dump(questions, quiz_file)
        quiz_file.close()
        key = f"qu-course-design/{course_id}/quiz.json"
        s3_client = S3FileManager()
        s3_client.upload_file(f"output/{course_id}/quiz/quiz.json", key)
        course["questions_file"] = "https://qucoursify.s3.us-east-1.amazonaws.com/" + key


    course["slides_links"] = slide_links
    course["course_names_slides"] = slide_names
    course["videos_links"] = video_links
    course["module_ids"] = module_ids
    course["course_module_information"] = course_module_information
    course["course_names_videos"] = slide_names
    course_design['modules'] = modules
    
    logging.info("Updating course design")
    course_design['status'] = "Published"
    mongo_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": course_design})

    return course

def _create_certificate(course_id, course_name):
    certificate = Image.open(open("dags/course/assets/QU-Certificate.jpg", "rb"))

    # Create an ImageDraw object to write on the image
    draw = ImageDraw.Draw(certificate)

    # Font settings (bold fonts)
    font_path_bold = "dags/course/assets/ArialBold.ttf"  # Replace with the path to a valid bold .ttf font file
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
                x_start = position[0] - line_width // 2  # Center-align horizontally
            elif align == "left":
                x_start = position[0]  # Left-aligned
            else:
                x_start = position[0] - line_width  # Right-aligned
            draw.text((x_start, position[1] + y_offset), line, font=font, fill=fill)
            y_offset += font.getbbox(line)[3] - font.getbbox(line)[1] + line_spacing

    # Certificate dimensions
    image_width, image_height = certificate.size

    # Title text position and wrapping
    title_position = (image_width // 2, 180)  # Centered horizontally
    max_width_title = certificate.size[0] + 200  # Leave some margin
    draw_wrapped_text(draw, title_text, font_title, title_position, max_width_title, (255, 255, 255), align="center", line_spacing=15)

    # Message text position and wrapping
    text_position_date = (50, 420)  # Left-aligned with a margin
    max_width_message = certificate.size[0] + 200  # Leave some margin
    draw_wrapped_text(draw, message_text, font_message, text_position_date, max_width_message, (0, 0, 0), align="left", line_spacing=10)

    # Save the modified image
    output_path = f'output/{course_id}/quiz_certificate.jpg'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    certificate.save(output_path)

    key = f"qu-course-design/{course_id}/quiz_certificate.jpg"
    s3_client = S3FileManager()
    s3_client.upload_file(output_path, key)
    
    return "https://qucoursify.s3.us-east-1.amazonaws.com/" + key

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
        mongo_client = AtlasClient()
        course = mongo_client.find("courses", filter={"course_id": ObjectId(course_id)})
        
        course = course[0]

        course = _update_modules(course_id, course)
        
        mongo_client.update("courses", filter={"course_id": ObjectId(course_id)}, update={"$set": course})
        
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
        mongo_client = AtlasClient()
        course = course_object
        course["course_id"] = ObjectId(course_id)

        certificate_path = _create_certificate()

        course["certificate_path"] = certificate_path

        course_design = mongo_client.find("course_design", filter={"_id": ObjectId(course_id)})
        if not course_design:
            return "Course design not found"
        
        course['app_name'] = course_design["course_name"]
        course["app_image_location"] = course_design["course_image"]
        course["short_description"] = course_design["course_description"]
        course["home_page_introduction"] = course_design["course_description"]
     

        course = _update_modules(course_id, course)

        mongo_client.insert("courses", course)
        
        return True
    
    except Exception as e:
        logging.error(f"Error in creating course: {e}")

