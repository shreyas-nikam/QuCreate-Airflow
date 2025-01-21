"""
Deliverables Consists of:
1. Slide_Generated: Generated slide using the content from the previous step.
2. Module Information: Markdown content for Module Information
3. Video: Video generated using the content from the previous step.
4. Assessment: Assessment generated using the content from the previous step.
"""
import os
import subprocess
from utils.s3_file_manager import S3FileManager
from utils.mongodb_client import AtlasClient
from bson.objectid import ObjectId
import logging
from pptx import Presentation
import fitz
import random
import multiprocessing
from pathlib import Path
import time
import azure.cognitiveservices.speech as speechsdk
from moviepy.editor import ImageClip, AudioFileClip, VideoFileClip, concatenate_videoclips
import json
import uuid
from utils.prompt_handler import PromptHandler
from utils.llm import LLM
from utils.retriever import Retriever


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
    
def _download_slide(slide_link):
    """
    Download the slide from the slide_link
    """
    try:
        s3_client = S3FileManager()
        slide_path = s3_client.download_file(slide_link)
        return slide_path
    except Exception as e:
        logging.error(f"Error in downloading slide: {e}")
        return None
    
def _get_slide_content(slide_link):
    """
    Get the slide content from the slide_content json file
    """
    try:
        s3_client = S3FileManager()
        slide_content = json.loads(s3_client.get_object(slide_link))
        return slide_content
    except Exception as e:
        logging.error(f"Error in getting slide content: {e}")
        return None
    
def _get_transcript_from_ppt(ppt):
    prs = Presentation(ppt)
    speaker_notes = []
    for slide in prs.slides:
        notes_slide = slide.notes_slide
        text_frame = notes_slide.notes_text_frame
        speaker_notes.append(text_frame.text.replace("�", ""))
    return speaker_notes


def _ppt_to_pdf(input_file, output_dir):
    """
    Convert a PowerPoint file to PDF using LibreOffice.
    
    :param input_file: Path to the .pptx file
    :param output_dir: Directory where the PDF will be saved
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"File {input_file} does not exist")
    
    if not os.path.isdir(output_dir):
        raise NotADirectoryError(f"{output_dir} is not a valid directory")
    
    # LibreOffice command to convert to PDF
    command = [
        "libreoffice",
        "--headless",
        "--convert-to", "pdf",
        "--outdir", output_dir,
        input_file
    ]
    
    subprocess.run(command, check=True)
    print(f"Converted {input_file} to PDF and saved in {output_dir}")

def _create_images(file_path, module_id):
    # Convert the ppt to pdf
    OUTPUT_PATH = "output"
    target_folder = Path(f"{Path(OUTPUT_PATH)}/{module_id}")
    _ppt_to_pdf(file_path, target_folder)


    # Convert pdf to images
    source_file = Path(f"{OUTPUT_PATH}/{module_id}/{module_id}.pdf")
    target_folder = Path(f"{Path(OUTPUT_PATH)}/{module_id}/images")
    Path(target_folder).mkdir(parents=True, exist_ok=True)


    if os.path.exists(source_file):
        doc = fitz.open(source_file)
        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            pix = page.get_pixmap()
            output = target_folder / f"{module_id}-{page_index}.png"
            pix.save(output)
        doc.close()



def _get_audio(module_id, text, filename):
    OUTPUT_PATH = "output"

    service_region = os.getenv("AZURE_TTS_SERVICE_REGION")
    speech_key = os.getenv("AZURE_TTS_SPEECH_KEY")


    speech_config = speechsdk.SpeechConfig(
        subscription=speech_key, region=service_region)
    speech_config.speech_synthesis_language = "en-US"
    speech_config.speech_synthesis_voice_name = "en-US-AvaNeural"


    filepath = Path(f"{OUTPUT_PATH}/{module_id}/audio")
    # Get the audio from the text


    # Create the folder if it does not exist
    Path(filepath).mkdir(parents=True, exist_ok=True)


    # Create the audio synthesizer
    audio_config = speechsdk.audio.AudioOutputConfig(
        filename=str(Path(f'{filepath}/{filename}')))
    speech_synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config, audio_config=audio_config)


    result = speech_synthesizer.speak_text_async(text).get()


    while not os.path.exists(Path(f'{filepath}/{filename}')):
        time.sleep(random.randint(5, 10))


    # Get the audio
    while result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:


        time.sleep(random.randint(15, 20))
        result = speech_synthesizer.speak_text_async(text).get()


        while not os.path.exists(Path(f'{filepath}/{filename}')):
            time.sleep(random.randint(5, 10))


        # Checks result.
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            break


        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print("Speech synthesis canceled: {}".format(
                cancellation_details.reason))
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                if cancellation_details.error_details:
                    print("Error details: {}".format(
                        cancellation_details.error_details))
            print("Did you update the subscription info?")


def _create_audio(module_id, transcript):
    # Create the audio
    OUTPUT_PATH = "output"
    audio_folder = Path(f"{Path(OUTPUT_PATH)}/{module_id}/audio")
    Path(audio_folder).mkdir(parents=True, exist_ok=True)


    # Iterate over the speaker notes for each .txt file
    for index, notes in enumerate(transcript):

        # Get the audio
        _get_audio(module_id, notes, f"audio_{index+1}.wav")


def stitch_videos(module_id, updation_map):
    OUTPUT_PATH = "output"
    video_files = list(updation_map.values())
    clips = [VideoFileClip(video_file) for video_file in video_files]
    final_clip = concatenate_videoclips(clips, method="compose")
    Path(f"{OUTPUT_PATH}/{module_id}").mkdir(parents=True, exist_ok=True)
    final_clip.write_videofile(
        str(Path(f"{OUTPUT_PATH}/{module_id}/{module_id}.mp4")), fps=10)


def _get_questions(module_content, num_questions=10):
    trials = 5
    prompt_handler = PromptHandler()
    llm = LLM()
    print("Getting questions")
    while trials > 0:
        print(trials)   
        try:
            prompt = prompt_handler.get_prompt("CONTENT_TO_QUESTIONS_PROMPT")
            response = llm.get_response(prompt, inputs={
                "CONTENT": module_content, "NUM_QUESTIONS": num_questions})
            try:
                response = response[response.find("["):response.rfind("]") + 1]
                return json.loads(response)
            except:
                return json.loads(response)
        except Exception as e:
            print(e)
            trials -= 1
            continue



def _save_questions(questions, module_id):
    OUTPUT_PATH = "output"
    with open(Path(f"{OUTPUT_PATH}/{module_id}/questions.json"), "w", encoding='utf-8') as file:
        file.write(json.dumps(questions))


def _get_questions_helper(module_content, module_id, chunk_size=20000):
    
    OUTPUT_PATH = "output"

    overall_questions = {}
    for module_id in os.listdir(f"{OUTPUT_PATH}/{module_id}"):

        try:
            print("Getting Questions for Module ", module_id)
            questions = []
            text = module_content
            # text_1 = text[:len(text)//2]
            # questions = _get_questions(text_1, 5)
            # text_2 = text[len(text)//2:]
            # questions.extend(_get_questions(text_2, 5))
            chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
            for chunk in chunks:
                questions.extend(_get_questions(chunk, 5))

            for index, question in enumerate(questions):
                questions[index]["uuid"] = str(uuid.uuid4())

            overall_questions[module_id] = questions
            _save_questions(overall_questions, module_id)
        except Exception as e:
            print(e)
            continue
    _save_questions(overall_questions, module_id)



def _add_silence_to_audio(module_id, audio_file_name):
    OUTPUT_PATH = "output"
    command = r"""ffmpeg -i ".\{output_path}\{module_id}\audio\{audio_file_name}" -i .\inputs\silence.wav -filter_complex "[0:a][1:a]concat=n=2:v=0:a=1" ".\{output_path}\{module_id}\audio\{new_audio_file_name}" -hide_banner -loglevel error""".format(
        output_path=OUTPUT_PATH, module_id=module_id, audio_file_name=audio_file_name, new_audio_file_name=audio_file_name.replace("_", "_with_silence_"))
    os.system(command)

def _create_video_parallel(module_id, slide_number, image):
    OUTPUT_PATH = "output"
    audio_folder = Path(f"{OUTPUT_PATH}/{module_id}/audio")
    video_folder = OUTPUT_PATH / f"{module_id}/video"
    img_clip = ImageClip(image)


    # Load audio file for the current slide
    _add_silence_to_audio(module_id, f"audio_{slide_number+1}.wav")


    audio_file_path = Path(
        f"{audio_folder}/audio_with_silence_{slide_number+1}.wav")
    audio_file = AudioFileClip(str(audio_file_path))


    # Set the duration of the text clip to match the audio duration
    img_clip = img_clip.set_duration(audio_file.duration)


    # Create a video for this current slide
    img_clip = img_clip.set_audio(audio_file)


    img_clip = img_clip.subclip(0, audio_file.duration)
    img_clip.write_videofile(str(Path(
        f"{video_folder}/slide_{slide_number+1}.mp4")), fps=10, verbose=False, logger=None)
    return slide_number+1, str(Path(f"{video_folder}/slide_{slide_number+1}.mp4"))




def _create_videos(module_id):
    updation_map = {}
    OUTPUT_PATH = "output"
    image_folder = Path(f"{OUTPUT_PATH}/{module_id}/images")
    audio_folder = Path(f"{OUTPUT_PATH}/{module_id}/audio")
    video_folder = Path(f"{OUTPUT_PATH}/{module_id}/video")
    Path(video_folder).mkdir(parents=True, exist_ok=True)


    # Get the sorted images
    search_dir = image_folder
    files = os.listdir(search_dir)
    files = [os.path.join(search_dir, f)
             for f in files]  # add path to each file
    files.sort(key=lambda x: os.path.getmtime(x))


    parallel_videos = [(module_id, i, img) for i, img in enumerate(files)]


    with multiprocessing.Pool(processes=1) as pool:
        results = pool.starmap(_create_video_parallel, parallel_videos)
        for slide_number, video_path in results:
            updation_map[slide_number] = video_path


    with open(Path(f"{OUTPUT_PATH}/{module_id}/updation_map.json"), "w", encoding='utf-8') as file:
        file.write(json.dumps(updation_map))


    stitch_videos(module_id, updation_map)

def _generate_video(slide_path, module_id):
    transcript = _get_transcript_from_ppt(slide_path)
    _create_images(slide_path, module_id)
    _create_audio(module_id, transcript)
    _create_videos(module_id)


def _generate_assessment(slide_content):
    """
    Generate the assessment from the slide content
    """
    try:
        module_content = slide_content
        questions = _get_questions_helper(module_content, 10)
        return questions
    except Exception as e:
        logging.error(f"Error in generating assessment: {e}")
        return None
    
    
def _generate_chatbot(source, destination):
    """
    Creates a retriever object for the course
    
    Args:
    source: Path to the folder containing the course content
    destination: Path to the folder where the retriever object will be saved
    """
    retriever = Retriever()

    Path(destination).mkdir(parents=True, exist_ok=True)

    retriever.create_vector_store(file_name=source, db_path=destination)


def upload_files(video_path, assessment, chatbot, module_id, resource_link):
    """
    Upload the video, assessment file, chatbot to s3
    """
    try:
        s3_client = S3FileManager()
        key = resource_link.split("/")[-1]
        video_key = resource_link.replace(key, f"{module_id}.mp4")
        video_link = s3_client.upload_file(video_path)

        assessment_key = resource_link.replace(key, f"{module_id}_assessment.json")
        assessment_link = s3_client.upload_file(assessment)

        # TODO
        chatbot_link = ""
        # chatbot_key = resource_link.replace(key, f"{module_id}_chatbot.pkl")
        # chatbot_link = s3_client.upload_file(chatbot)


        return video_link, assessment_link, chatbot_link
    except Exception as e:
        logging.error(f"Error in uploading files: {e}")
        return None, None, None
    
def update_module_with_deliverables(module, video_link, assessment_link, chatbot_link, module_id, course, course_id):
    """
    Update the module with the video, assessment, chatbot links in pre_processed_deliverables
    """
    try:
        module["pre_processed_deliverables"] = [
            {
                "resource_type": "Video",
                "resource_link": video_link,
                "resource_name": f"{module_id}.mp4",
                "resource_description": "Video generated from the slide content",
                "resource_id": ObjectId()
            },
            {
                "resource_type": "Assessment",
                "resource_link": assessment_link,
                "resource_name": f"{module_id}_assessment.json",
                "resource_description": "Assessment generated from the slide content",
                "resource_id": ObjectId()
            },
            # TODO for chatbot
        ]

        for index in range(len(course["modules"])):
            if course["modules"][index]["module_id"] == module_id:
                course["modules"][index] = module
                break

        mongodb_client = AtlasClient()
        mongodb_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": {"modules": course["modules"]}})

        course["status"] = "Deliverables Review"
        mongodb_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": {"status": "Deliverables Review"}})
        
    except Exception as e:
        logging.error(f"Error in updating module with deliverables: {e}")

async def process_deliverables_request(course_id, module_id):
    """
    Steps:
    1. Get the course and module object from the course_id and module_id
    2. Get the slide from the pre_processed_content
    3. Generate the video from the slide
    4. Extract the content from the slide
    5. Create an assessment based on the content from the slide
    6. Create a chatbot based on the content from the slide
    7. Upload the video, assessment file, chatbot to s3
    8. Update the module with the video, assessment, chatbot links in pre_processed_deliverables
    9. Update the status of the course to Deliverables Review
    """

    course, module = _get_course_and_module(course_id, module_id)
    slide_link = _get_resource_link(module)
    downloaded_slide_path = _download_slide(slide_link)
    slide_content = _get_slide_content(slide_link)
    video_path = _generate_video(downloaded_slide_path, module_id)
    assessment = _generate_assessment(slide_content)
    chatbot = _generate_chatbot(slide_content)
    video_link, assessment_link, chatbot_link = upload_files(video_path, assessment, chatbot)
    update_module_with_deliverables(module, video_link, assessment_link, chatbot_link)
    return True
