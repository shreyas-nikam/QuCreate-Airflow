"""
Structure Consists of:
1. Slide_Generated: Generated slide using the content from the previous step.
2. Module Information: Markdown content for Module Information
"""
import os
from utils.s3_file_manager import S3FileManager
from utils.mongodb_client import AtlasClient
from bson.objectid import ObjectId
import json
import logging
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt


def _get_course_and_module(course_id, module_id):
    """
    Get the course and module object from the course_id and module_id
    """
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


def _get_resource_link(module):
    """
    Get the slide content from the module
    """
    try:
        for obj in module["pre_processed_content"]:
            if obj["resource_type"] == "Slide_Content":
                return obj["resource_link"]
        
        return None
    
    except Exception as e:
        logging.error(f"Error in getting slide content: {e}")
        return None


def _extract_content(slide_content):
    """
    Extract the slide content from the slide_content json file
    """
    try:
        s3_client = S3FileManager()
        slide_content = json.loads(s3_client.get_object(slide_content))

        markdown = ""
        transcript = []

        for slide in slide_content:
            markdown += f"# {slide['slide_header']}\n\n{slide['slide_content']}\n\n"
            transcript.append(slide["speaker_notes"])

        return markdown, transcript
    
    except Exception as e:
        logging.error(f"Error in extracting content: {e}")
        return None, None


def _generate_pptx(markdown):
    """
    Generate the pptx file using the markdown content
    """
    try:
        # write the file in a temp location
        with open("/tmp/content.md", "w") as f:
            f.write(markdown)
        
        md_file_path = Path("/tmp/content.md")
        output_ppt_path = Path("/tmp/content.pptx")

        # Generate the pptx file in a temp location
        os.system(f'python md2pptx/md2pptx.py "{str(output_ppt_path.absolute())}" < "{str(md_file_path.absolute())}"')

        return "/tmp/content.pptx"
    
    except Exception as e:
        logging.error(f"Error in generating pptx: {e}")
        return None
    

def _format_ppt(output_ppt_path, speaker_notes,
               logo_path="assets/logo.jpg",
               header='assets/top.png'):

    Path(output_ppt_path).parent.mkdir(parents=True, exist_ok=True)

    prs = Presentation(output_ppt_path)


    # remove first slide from ppt
    del prs.slides._sldIdLst[0]


    prs.save(output_ppt_path)


    # Reopen the presentation to save the changes
    prs = Presentation(output_ppt_path)


    slide_number = 0
    for slide in prs.slides:


        if slide_number > 0:
            # move the title and content down by one inch
            top_margin = 0.7
            for shape in slide.shapes:
                if shape.has_text_frame:
                    shape.top = Inches(top_margin)
                    top_margin = 1.5


        # add speaker notes to all slides
        try:
            notes_slide = slide.notes_slide
            text_frame = notes_slide.notes_text_frame
            text_frame.text = speaker_notes[slide_number]
        except Exception as e:
            pass


        # Add logo to the bottom right corner of each slide
        left = prs.slide_width - Inches(1)
        top = prs.slide_height - Inches(0.65)
        width = Inches(1)
        slide.shapes.add_picture(logo_path, left, top, width=width)


        # Add header to the top of each slide
        left = 0
        top = 0
        width = prs.slide_width
        slide.shapes.add_picture(header, left, top, width=width)


        # Add page number to the top right corner of each slide
        left = prs.slide_width - Inches(0.5)
        top = Inches(0.5)
        width = Inches(0.5)
        slide_number_box = slide.shapes.add_textbox(
            left, top, width, width)
        text_frame = slide_number_box.text_frame
        p = text_frame.add_paragraph()
        p.text = f"{slide_number+1}"
        p.margin_top = 0
        p.font.bold = True


        slide_number += 1

    prs.save(output_ppt_path)
    prs = Presentation(output_ppt_path)
    prs.save(output_ppt_path)


def _add_transcript_to_pptx(pptx_file, transcript):
    try:
        _format_ppt(pptx_file, transcript)
        return pptx_file
    except Exception as e:
        logging.error(f"Error in adding transcript to pptx: {e}")
        return None


async def _save_file_to_s3(pptx_file, key):
    try:
        s3_client = S3FileManager()
        key = key.replace("pre_processed_content", "pre_processed_structure")
        key = key.replace("Slide_Content.json", "Slide_Generated.pptx")
        await s3_client.upload_file(pptx_file, key)
        # delete the temp file
        os.remove(pptx_file)
        return key
    except Exception as e:
        logging.error(f"Error in saving file to s3: {e}")
        return None


def _update_slide_entry(course_id, course, module, resource_link):
    try:
        mongodb_client = AtlasClient()
        s3_client = S3FileManager()

        resource = {
            "resource_link": resource_link,
            "resource_type": "Slide_Generated",
            "resource_name": "Slide Generated",
            "resource_description": "Slide Generated from the content",
            "resource_id": ObjectId()
        }

        if "pre_processed_structure" not in module:
            module["pre_processed_structure"] = []

        module["pre_processed_structure"].append(resource)

        # add the other resources to the module except for the Slide_Content
        for obj in module["pre_processed_content"]:
            if obj["resource_type"] != "Slide_Content":
                # copy the object to the new s3 location
                prev_location = obj["resource_link"]
                new_location = prev_location.replace("pre_processed_content", "pre_processed_structure")
                
                s3_client.copy_file(prev_location, new_location)

                resource = {
                    "resource_link": new_location,
                    "resource_type": obj["resource_type"],
                    "resource_name": obj["resource_name"],
                    "resource_description": obj["resource_description"],
                    "resource_id": ObjectId()
                }
                module["pre_processed_structure"].append(resource)

        for i in range(len(course["modules"])):
            if course["modules"][i]["module_id"] == module["module_id"]:
                course["modules"][i] = module
        
        course["status"] = "Content Review"
        
        mongodb_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": {"modules": course["modules"]}})

        return True
    
    except Exception as e:
        logging.error(f"Error in updating entry: {e}")


async def process_structure_request(course_id, module_id):
    """
    Steps:
    1. Get mongodb object the course id, module id in the course_design collection.
    2. Get the json file with the reviewed content from object's pre_processed_content object's resource_link of resource_type Slide_Content.
    3. Get the file from s3. Extract the sldie_header, slide_content, speaker_notes from the json file and convert the slide_header and slide_content to markdown.
    4. Generate the pptx file using the markdown file.
    5. Extract the transcript from the jso
    """

    course, module = _get_course_and_module(course_id, module_id)
    slide_content = _get_resource_link(module)
    markdown, transcript = _extract_content(slide_content)
    pptx_file = _generate_pptx(markdown)
    pptx_file_with_transcript = _add_transcript_to_pptx(pptx_file, transcript)
    resource_link = await _save_file_to_s3(pptx_file_with_transcript, resource_link)
    updated_slide = _update_slide_entry(course_id, course, module, resource_link)



    



