import concurrent.futures
import json
import uuid
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# from utils.llm import llm  # your custom LLM wrapper
from utils.llm import LLM
from utils.s3_file_manager import S3FileManager  

from langchain.prompts.prompt import PromptTemplate
import asyncio
import logging
from pathlib import Path

# Todo:
# Adding disclaimerL This concept card was generated using -> point it to the course landing page. (PDF)


s3_file_manager = S3FileManager()
llm = LLM()

TITLE = "Adversarial Machine Learning Terminology"
FILE_INPUT_S3_LINK = "https://qucoursify.s3.us-east-1.amazonaws.com/qu-glossary-design/glossary_data.json"


DEFINITION_PROMPT = """
You are an assistant. Please provide a thorough extended definition for the term below.
- Provide a deeper and more comprehensive explanation of the term beyond the basic definition. Add sources if sourcing from internet/wikipedia  
- Include how it fits into the larger context of machine learning, adversarial threats, or system security.  
- Return Markdown and bullet points for the explanation.  
(Use emojis wherever possible, add highlighting for important terms, makrdown for visually appealing formatting)

Return only markdown in this exact format (no extra text):

```markdown
### Definition
Add **definition** here with **important** points highlighted.

- Add bullet points with proper **highlighting** here

### Key things to know
- Add key things to know here **highlighted** appropriately

### Examples
#### Example title
Example description
#### Example title 2
Example description 2
```

Term: 
{TERM}

Short definition: 
{DEFINITION}
"""


GET_IMAGE_PROMPT = """
You are an assistant. Please provide a very detailed and realistic image prompt for the term below.
- The image should be visually appealing and relevant to the term.
- The image should be in a corporate or organizational setting.
- The image should be in a 16:9 aspect ratio.
- The image should be in a 4k resolution.
- The image should be in a realistic style.

Term:
{TERM}

Definition:
{DEFINITION}

Extended Definition:
{EXTENDED_DEFINITION}
"""

SCENARIO_PROMPT = """
Describe a very detailed, realistic scenario or case study where the given term plays a central role. Your scenario must:
- Have at least 5-10 sentences for the scenario_description.
- Be situated in a real-world organizational or corporate setting. (Use real world use cases if possible)
- Explain how the attack or event affected the organization (consequences/damages).
- Clearly describe:
  - **How it was identified**
  - **How it was controlled**
  - **How it was mitigated**
  
  
Return only JSON in this exact format (no extra text):

```json
{{
  "scenario_description": "...",
  "impact": "...",
  "identification": "...",
  "control": "...",
  "mitigation": "..."
}}
```

Term: 
{TERM}

Definition: 
{DEFINITION}

Extended Definition: 
{EXTENDED_DEFINITION}
"""

REFERENCES_PROMPT = """
Add references and additional reading for the term and defintion below. Return it in the form of markdown list, hyperlinked properly.
Return only markdown in this exact format (no extra text):
```markdown
### References and Additional Readings
- [Reference 1](link)
- [Reference 2](link)
```

Term:
{TERM}

Definition:
{DEFINITION}

Extended Definition:
{EXTENDED_DEFINITION}
"""

QUIZ_PROMPT = """
You are given a term and a scenario. Generate exactly 4 multiple-choice questions in JSON format.
As a part of the learning outcome statement, 
we expect the user to understand the concept, the identification, mitigation and the control of the adversarial attack specific to the topic.
When creating this assessment, ensure that the reviewer understands the concept and is able to apply it to a specific scenario with understanding of the concept, 
the identification, the control and the mitigation of the scenario.

Each question must address one of:
- Topic
- Identification
- Control
- Mitigation

Return only JSON in this format (no extra text):

```json
{{
  "quiz": [
    {{
      "question": "...",
      "options": ["A: option A", "B: option B", "C: option C", "D: option D"],
      "correct_answer": "A",
      "hint": "...",
      "explanation": "..."
    }},
    ...
  ]
}}
```

Term: 
{TERM}

Definition:
{DEFINITION}

Scenario: 
{SCENARIO}
"""

JUDGE_PROMPT = """
You are a judge. Evaluate the quiz JSON to see if it sufficiently tests knowledge of:
- The topic
- How to identify it
- How to control it
- How to mitigate it
The quiz is expected to meet the competency for the term and scenario provided.

If it is sufficient, return the same quiz JSON unchanged.
If it is not sufficient, correct or improve the questions, answers, hints, or explanations.
Return only JSON in the same format (no extra text), for example:

```json
{{
  "quiz": [
    {{
      "question": "...",
      "options": ["A","B","C","D"],
      "correct_answer": "A",
      "hint": "...",
      "explanation": "..."
 }},
    ...
  ]
}}
```

Here is the term and scenario for reference:
Term: 
{TERM}

Scenario: 
```
{SCENARIO}
```

Here is the quiz JSON to evaluate:
{QUIZ_JSON}
"""

# ------------------------------------------------------------------------
# DAG DEFINITION
# ------------------------------------------------------------------------
default_args = {
    "owner": "airflow",
    "start_date": datetime(2023, 1, 1),
    "retries": 0,
    "retry_delay": timedelta(minutes=1),
}

with DAG(
    dag_id="glossary_pipeline",
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
) as dag:
    
    def write_to_file(term, response_str):
        with open("errored_responses.txt", "a") as f:
            f.write(f"Term: {term}\n")
            f.write(f"Response: {response_str}\n\n")
            
            
    def fetch_glossary(s3_file_path, **context):
        """
        1) Fetch the glossary data from S3.
        2) Store in XCom for later tasks.
        """
        glossary_data = {}
        # Fetch from S3
        key = s3_file_path.split("https://qucoursify.s3.us-east-1.amazonaws.com/")[-1]
        response = s3_file_manager.get_object(key)
        glossary_data = json.loads(response['Body'].read().decode('utf-8'))
        
        context["ti"].xcom_push(key="glossary_data", value=glossary_data)

    def definition_task(**context):
        """
        1) For each term, call the LLM to get an extended definition (JSON only).
        2) Use multithreading to speed up calls.
        3) Store partial results in XCom: { term -> { extended_definition: ... } }.
        """

        def fetch_definition(term, definition):
            prompt = PromptTemplate(template=DEFINITION_PROMPT, inputs=["TERM", "DEFINITION"])
            response_str = llm.get_response(prompt, inputs={"TERM":term, "DEFINITION":definition}).strip()
            # Attempt JSON parse
            try:
                resp_json = response_str[response_str.index("```markdown")+11 : response_str.rindex("```")]
                return term, resp_json
            except Exception:
                write_to_file(term, response_str)
                return term, ""

        partial_data = {}
        glossary_data = context["ti"].xcom_pull(task_ids="fetch_glossary", key="glossary_data")
        print(f"Fetched {len(glossary_data)} terms from glossary data")
        # You can tune max_workers to your environment / concurrency limits
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for term, definition in glossary_data.items():
                future = executor.submit(fetch_definition, term, definition)
                futures.append(future)

            for f in concurrent.futures.as_completed(futures):
                term_res, extended_def = f.result()
                partial_data[term_res] = {
                    "term": term_res,
                    "definition": glossary_data[term_res],
                    "extended_definition": extended_def
                }

        # Store in XCom
        context["ti"].xcom_push(key="definitions", value=partial_data)

    def scenario_task(**context):
        """
        1) Get definitions from XCom
        2) For each term, call the LLM to get a scenario in JSON
        3) Use multithreading again
        4) Merge with existing data
        """
        ti = context["ti"]
        definitions_data = ti.xcom_pull(task_ids="definition_task", key="definitions")

        def fetch_scenario(term, defintion, extended_definition, existing_record):
            prompt = PromptTemplate(template=SCENARIO_PROMPT, inputs=["TERM"])
            
            response_str = llm.get_response(prompt, inputs={"TERM":term, "DEFINITION": definition, "EXTENDED_DEFINITION": extended_definition}).strip()
            try:
                resp_json = json.loads(response_str[response_str.index("```json")+7 : response_str.rindex("```") ])
                return term, resp_json
            except json.JSONDecodeError:
                write_to_file(term, response_str)
                return term, ""

        updated_data = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for term, record in definitions_data.items():
                definition = record["definition"]
                extended_definition = record["extended_definition"]
                
                future = executor.submit(fetch_scenario, term, definition, extended_definition, record)
                futures.append(future)

            for f in concurrent.futures.as_completed(futures):
                term_res, scenario_desc = f.result()
                existing = definitions_data[term_res]
                updated_data[term_res] = {
                    "term": term_res,
                    "definition": existing["definition"],
                    "extended_definition": existing["extended_definition"],
                    "scenario_description": scenario_desc
                }

        ti.xcom_push(key="scenario_data", value=updated_data)

    def quiz_task(**context):
        """
        1) Get scenario_data from XCom
        2) For each term, call the LLM to generate exactly 4 questions
           in JSON about (topic, identification, control, mitigation).
        3) Use multithreading
        4) Merge data
        """
        ti = context["ti"]
        scenario_data = ti.xcom_pull(task_ids="scenario_task", key="scenario_data")

        def fetch_quiz(term, definition, existing_record):
            scenario_text = existing_record["scenario_description"]
            prompt = PromptTemplate(template=QUIZ_PROMPT, inputs=["TERM", "SCENARIO"])
            response_str = llm.get_response(prompt, inputs={"TERM":term, "DEFINITION": definition, "SCENARIO":scenario_text}).strip()
            try:
                resp_json = json.loads(response_str[response_str.index("```json")+7 : response_str.rindex("```")])
                return term, resp_json.get("quiz", [])
            except json.JSONDecodeError:
                write_to_file(term, response_str)
                return term, []

        updated_data = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for term, record in scenario_data.items():
                definition = record["extended_definition"]
                future = executor.submit(fetch_quiz, term, definition, record)
                futures.append(future)

            for f in concurrent.futures.as_completed(futures):
                term_res, quiz_list = f.result()
                existing = scenario_data[term_res]
                updated_data[term_res] = {
                    "term": term_res,
                    "definition": existing["definition"],
                    "extended_definition": existing["extended_definition"],
                    "scenario_description": existing["scenario_description"],
                    "quiz": quiz_list
                }

        ti.xcom_push(key="quiz_data", value=updated_data)
        
    # def image_task(**context):
    #     """
    #     1) Get term, defintion, extended_defintion from XCom
    #     2) For each term, call the LLM to get image prompt in JSON
    #     3) Use multithreading
    #     4) Merge data
    #     """
        
    #     ti = context["ti"]
    #     glossary_data = ti.xcom_pull(task_ids="fetch_glossary", key="glossary_data")
    #     definitions_data = ti.xcom_pull(task_ids="definition_task", key="definitions")

    #     def fetch_image(term, definition, extended_definition):
    #         import openai   
    #         image_response = openai.Image.create(
    #             model
    #             prompt=GET_IMAGE_PROMPT.format(TERM=term, DEFINITION=definition, EXTENDED_DEFINITION=extended_definition),
    #             n=1,
    #             size="1024x1024"
    #         )
    #         image_url = image_response['data'][0]['url']
    #         # download the image
    #         image_path = f"output/images/{term}.png"
    #         image_response = requests.get(image_url)
    #         with open(image_path, 'wb') as f:
    #             f.write(image_response.content)
                
    #         # upload to S3
    #         image_id = str(uuid.uuid4())
    #         key = f'qu-glossary-design/images/{image_id}.png'
    #         asyncio.run(s3_file_manager.upload_file(image_path, key))
    #         s3_url = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"
    #         # delete the local image
    #         os.remove(image_path)
                
    #         return term, s3_url
        

    #     updated_data = {}
    #     with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    #         futures = []
    #         for term in glossary_data.keys():
    #             definition = definitions_data[term]["definition"]
    #             extended_definition = definitions_data[term]["extended_definition"]
                
    #             future = executor.submit(fetch_image, term, definition, extended_definition)
    #             futures.append(future)

    #         for f in concurrent.futures.as_completed(futures):
    #             term_res, image_url = f.result()
    #             updated_data[term_res] = {
    #                 "term": term_res,
    #                 "image_url": image_url
    #             }

    #     ti.xcom_push(key="image_data", value=updated_data)

    
    def judge_task(**context):
        """
        1) For each term, pass the quiz JSON to the judge prompt.
        2) If it's sufficient, returns same quiz. Otherwise, the LLM updates it.
        3) Use multithreading
        4) Merge into final structure
        """
        ti = context["ti"]
        quiz_data = ti.xcom_pull(task_ids="quiz_task", key="quiz_data")
        if not quiz_data:
            print("No quiz data found. Exiting.")
            return None

        def judge_quiz(term, existing_record):
            quiz_list = existing_record["quiz"]
            scenario = existing_record["scenario_description"]
            quiz_json_str = json.dumps({"quiz": quiz_list}, ensure_ascii=False)
            prompt = PromptTemplate(template=JUDGE_PROMPT, inputs=["TERM", "QUIZ_JSON", "SCENARIO"])

            response_str = llm.get_response(prompt, inputs={"TERM":term, "QUIZ_JSON":quiz_json_str, "SCENARIO":scenario}).strip()
            try:
                resp_json = json.loads(response_str[response_str.index("```json")+7 : response_str.rindex("```")])
                final_quiz = resp_json.get("quiz", [])
            except json.JSONDecodeError:
                write_to_file(term, response_str)
                final_quiz = quiz_list

            return term, final_quiz

        judged_data = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for term, record in quiz_data.items():
                future = executor.submit(judge_quiz, term, record)
                futures.append(future)

            for f in concurrent.futures.as_completed(futures):
                term_res, final_quiz = f.result()
                existing = quiz_data[term_res]
                judged_data[term_res] = {
                    "term": term_res,
                    "definition": existing["definition"],
                    "extended_definition": existing["extended_definition"],
                    "scenario_description": existing["scenario_description"],
                    "quiz": final_quiz
                }

        ti.xcom_push(key="judged_data", value=judged_data)
        
    def references_task(**context):
        """
        1) Get term, defintion, extended_defintion from XCom
        2) For each term, call the LLM to get references in Markdown
        3) Use multithreading
        4) Merge data
        """
        
        ti = context["ti"]
        judged_data = ti.xcom_pull(task_ids="judge_task", key="judged_data")
        

        def fetch_references(term, definition, extended_definition):
            prompt = PromptTemplate(template=REFERENCES_PROMPT, inputs=["TERM"])
            response_str = llm.get_response(prompt, inputs={"TERM":term, "DEFINITION": definition, "EXTENDED_DEFINITION": extended_definition}).strip()
            try:
                resp_json = response_str[response_str.index("```markdown")+11 : response_str.rindex("```")]
                return term, resp_json
            except json.JSONDecodeError:
                write_to_file(term, response_str)
                return term, ""

        updated_data = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for term in judged_data.keys():
                definition = judged_data[term]["definition"]
                extended_definition = judged_data[term]["extended_definition"]
                
                future = executor.submit(fetch_references, term, definition, extended_definition)
                futures.append(future)

            for f in concurrent.futures.as_completed(futures):
                term_res, references_list = f.result()
                updated_data[term_res] = {
                    "term": term_res,
                    "definition": judged_data[term_res]["definition"],
                    "extended_definition": judged_data[term_res]["extended_definition"],
                    "scenario_description": judged_data[term_res]["scenario_description"],
                    "quiz": judged_data[term_res]["quiz"],
                    "references": references_list
                }
            

        ti.xcom_push(key="references_data", value=updated_data)

    def store_results_task(**context):
        """
        1) Gather the final judged data.
        2) Convert to a list of records.
        3) Write to a single local JSON file with a unique ID.
        4) (Optionally) upload it to S3 or somewhere else.
        """
        ti = context["ti"]
        final_data = ti.xcom_pull(task_ids="references_task", key="references_data")
        if not final_data:
            print("No final data found. Exiting.")
            return None

        results_list = []
        for term, content in final_data.items():
            results_list.append(content)

        run_id = str(uuid.uuid4())
        out_path = f"output/glossary-design/glossary_results_{run_id}.json"
        
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)

        results_json = {
            "title": TITLE,
            "terms": results_list
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results_json, f, indent=2)

        print(f"Stored final results at: {out_path}")
        ti.xcom_push(key="final_results_path", value=out_path)
        
    
        

    def store_output_in_s3(**context):
        ti = context["ti"]
        out_path = ti.xcom_pull(task_ids="store_results_task", key="final_results_path")
        id = str(uuid.uuid4())
        key = f'qu-glossary-design/{id}.json'
        logging.info(f"Uploading {out_path} to S3 with key {key}")
        asyncio.run(s3_file_manager.upload_file(out_path, key))
        print(f"Uploaded to S3: {key}")
        
        # store it in mongodb
        from utils.mongodb_client import AtlasClient
        mongo_client = AtlasClient()
        mongo_id = mongo_client.insert("qu-glossary-design", {
            "s3_file_key": key,
            "created_at": datetime.now(),
            "title": TITLE,
        })
        
        return {"_id": str(mongo_id), "s3_file_key": key}

    # --------------------------------------------------------------------
    # DEFINE TASKS
    # --------------------------------------------------------------------
    fetch_glossary_op = PythonOperator(
        task_id="fetch_glossary",
        python_callable=fetch_glossary,
        op_args=[FILE_INPUT_S3_LINK],
        provide_context=True
    )
    
    definition_op = PythonOperator(
        task_id="definition_task",
        python_callable=definition_task,
        provide_context=True,
    )

    scenario_op = PythonOperator(
        task_id="scenario_task",
        python_callable=scenario_task,
        provide_context=True,
    )

    quiz_op = PythonOperator(
        task_id="quiz_task",
        python_callable=quiz_task,
        provide_context=True,
    )
    
    references_op = PythonOperator(
        task_id="references_task",
        python_callable=references_task,
        provide_context=True,
    )

    judge_op = PythonOperator(
        task_id="judge_task",
        python_callable=judge_task,
        provide_context=True,
    )

    store_op = PythonOperator(
        task_id="store_results_task",
        python_callable=store_results_task,
        provide_context=True,
    )
    
    store_s3_op = PythonOperator(
        task_id="store_output_in_s3",
        python_callable=store_output_in_s3,
        provide_context=True,
    )
    

    # --------------------------------------------------------------------
    # SET TASK DEPENDENCIES
    # --------------------------------------------------------------------
    fetch_glossary_op >> definition_op >> scenario_op >> quiz_op >> judge_op >> references_op >> store_op >> store_s3_op
    