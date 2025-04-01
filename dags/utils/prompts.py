
prompts = {

    "CONTENT_TO_QUESTIONS_PROMPT": """
You are given the content for a module. You need to create {NUM_QUESTIONS} scenario based questions from the content.
Each question object should have the following keys: "question", "options", "answer_option", and "explanation".
All questions should have at least 4 options and the answer must be in one of the options.
Do not return anything other than the output json.
Have scenario-based questions. For the scenarios add the context to every question that is generated.
Have 2-3 questions per scenario.

Instructions:
The questions must be comprehensive and not superficial.
The explanations should be detailed.
The questions should focus on the important points in each part.
The quesstions should be scenario based.


Sample Questions:

Question: An analyst is valuing an electric utility with a dividend payout ratio of 0.65, a beta of 0.565,
and an expected earnings growth rate of 0.032. A regression on other electric utilities
produces the following equation:
Predicted P/E = 8.57 + (5.38 x dividend payout) + 15.53 x growth) - (0.61 x beta)
The predicted P/E on the basis of the values of the explanatory variables for the company is
closest to:
Options:
A. 12.2
B. 15.4
C. 20.8
D. 23.1
Answer: B
Explanation: The firm's PEG is 18.75 / 15. 32 = 1.22. Given the comparable group median PEG is 0.92, it appears
that Nuts, Inc. may be overvalued.

Question: Nuts, Inc. has a trailing P/E of 18.75 and a 5-year consensus growth rate forecast of
15.32%. The median PEG, based on leading P/E, for a group of companies comparable in
risk to Nuts, Inc. is 0.92. The stock appears to be:
Options:
A. Overvalued because its PEG ratio is 0.82
B. Overvalued because its PEG ratio is 1.22
C. Undervalued because its PEG ratio is 0.82
D. Undervalued because its PEG ratio is 1.22
Answer: A
Explanation: Predicted P/E = 8.57 + (5.38 x 0.65) + (15.53 x 0.032) - (0.61 x 0.56) = 12.2


Output format:
[
    {{
        "question": "What is the capital of France?",
        "options": ["Paris", "London", "New York", "Tokyo"],
        "answer_option": "a",
        "explanation": "The capital of France is Paris"
    }},
    {{
        "question": "What is the capital of India?",
        "options": ["Mumbai", "Kolkata", "Delhi", "Pune"],
        "answer_option": "c",
        "explanation": "The capital of India is Delhi"
    }}...
]

Do the above for the given content below:


Input:
Content: {CONTENT}
""",


    "CONTENT_TO_SPEAKER_NOTES_PROMPT": """
You are given the content for a slide in a module and the context of the content. You need to create speaker notes for the slide only based on the slide content.
The speaker notes should be in a neutral tone with a continuous flow.  
Do not expand acronyms in the speaker notes.
Do not have any opening remarks like hello, welcome or ending remarks like thank you in the speaker notes.  
Do not return anything other than the output string.  
Speak in continuation as if you were continuing from the previous slide. Do not use comments like 'today, we will discuss', 'in this slide', 'this slide discusses', etc. in the speaker notes.  
For formulae, do not use latex content, instead use words appropriate for the formulae so that they can be converted to audio.  
Input:  
Content:  
{CONTENT}  
Context:  
{CONTEXT}
""",

    "GET_MD_CONTENT_PROMPT": """
You are given the content that is to be put on a slide. You need to summarize the content in a markdown format that can be used for a slide.
You are catering to a professional audience. The content should be concise and to the point.
Instructions:  
1. Summarize the content in 4-5 bullet points. If the content exceeds 5 points, create new bulleted slide pages with appropriate headers (3 #s). The maximum number of words per slide should not exceed 200 words.  
2. Give me the output in the given example Markdown format only.  
3. If you need to span multiple slides, use ### with the new header. The headers should not be long and appropriate for the content on the slide.  
4. Bullet points should compulsorily begin with a *.  
5. Do not have any headers with less than 3 #s.


Example output markdown format:  
```markdown


* In a point, here's an [URL to example](https://www.example.com). This explains why this url is important.
* One  
    * One A focuses on **this** point that speaks about the importance of this point that is highlighted in bold.
    * One B has this **important point** that is crucial for understanding the content. All the highlighted points should be in bold.
* Two is the second point that is important for the content.
* Three is the third point that is important for the content.


### Image header

![Image Description in detail for speaker notes](path/to/image.jpg)


### Topic A - Part Two
* Two  
    * Two A is the sub-point of Two that explains the importance of the point.
    * Two B is another sub-point that is crucial for understanding the content.
* Three is the third point that is important for the content.


### Topic A - Third Part
* Four 
    * Four A is the sub-point of Four that explains the importance of the point.
    * Four B is another sub-point that is crucial for understanding the content.
* Five
    * Five A is the sub-point of Five that explains the importance of the point.
    * Five B is another sub-point that is crucial for understanding the content.
```


Content:  
{CONTENT}
""",

    "CONTENT_TO_SUMMARY_PROMPT": """
You are given the content for a module. You need to write a summary of the content in 2 sentences and 3-5 short bullet points.
The tone should be as if you are talking about what the course module will cover.
The summary should be concise and cover the main points of the content.
Do not return anything other than the output string.

Output format:
"Summary of the content in 2 sentences and 3-5 bullet points."
""",

    "COURSE_OUTLINE_TO_DF_PROMPT": """
You are given a course outline. You need to return a list of dictionary objects where each dictionary object represents a module in the course outline, having module_name and slide_header.

Instructions:
Do not return anything other than the list of dictionary objects.
The slide headers will be used for researching the topics. The slide headers belonging to the same module, will be in the same presentation. So make sure to have a continuous flow of topics in the same module.

Example:

Input:

### **Module 1: Automated Financial Content Generation**

- **AI in Financial Report Writing**
 - AI-powered tools for automatic generation of financial reports, quarterly earnings, and forecasts
 - Example: BloombergGPT for producing financial summaries and analyses 

- **Natural Language Processing (NLP) in Finance**
 - How NLP models can automate content such as market commentary, regulatory documents, or credit analysis
 - Example: JP Morgan's AI applications in creating research reports

- **Generative AI for Marketing and Client Engagement**
 - Personalized content marketing and customer engagement at scale
 - Example: Leveraging AI to generate personalized recommendations for cross-selling financial products


### **Module 2: AI in Financial Risk Management**

- **Predictive Analytics for Risk Assessment**
    - AI models for predicting market trends, credit risks, and investment opportunities
    - Example: AI-driven risk assessment tools for detecting fraudulent activities
	
- **AI in Fraud Detection and Prevention**
    - Machine learning algorithms for identifying anomalies and suspicious activities
    - Example: Mastercard's AI-powered fraud detection system
	
- **Automated Compliance Monitoring**

Output:
[{{"module_name": "Automated Financial Content Generation", "slide_header": "AI in Financial Report Writing - AI-powered tools for automatic generation of financial reports, quarterly earnings, and forecasts"}},
{{"module_name": "Automated Financial Content Generation", "slide_header": "Natural Language Processing (NLP) in Finance - How NLP models can automate content such as market commentary, regulatory documents, or credit analysis"}},
{{"module_name": "Automated Financial Content Generation", "slide_header": "Generative AI for Marketing and Client Engagement - Personalized content marketing and customer engagement at scale"}},
{{"module_name": "AI in Financial Risk Management", "slide_header": "Predictive Analytics for Risk Assessment - AI models for predicting market trends, credit risks, and investment opportunities"}},
{{"module_name": "AI in Financial Risk Management", "slide_header": "AI in Fraud Detection and Prevention - Machine learning algorithms for identifying anomalies and suspicious activities"}},
{{"module_name": "AI in Financial Risk Management", "slide_header": "Automated Compliance Monitoring"}}]


Input:
Course Outline: {COURSE_OUTLINE}

Output format:
[{{"module_name": "module1", "slide_header": "slide1"}}, {{"module_name": "module2", "slide_header": "slide2"}}, ...]

Output:

""",

    "GET_RESEARCH_CONTENT_PROMPT": """
I am working on the module {MODULE_NAME} and I need detailed research notes on the topic {TOPIC_NAME}. 
Please provide an in-depth explanation that includes key concepts, theories, examples, links to images, links to diagrams, and any important studies or data related to the topic. 
Organize the notes in a clear and structured way, with headings and subheadings if necessary. Make sure the notes are suitable for academic research, including any relevant citations or references to major works in this area.
""",

    "GET_OUTLINE_PROMPT": """
You are creating an outline for a presentation for a course. 
For all the material that is uploaded, create an outline based on the user's instructions.
The outline should be structured and organized in a logical flow.
The outline should have a header, bullet points in markdown format.
Each Slide should cover the minimum content that can be covered in a slide. Do not have too much content on a single slide.
The slides should have a continuous flow and should not be disjointed.

Output format:
```markdown
# Slide 1:
- Point 1
- Point 2
- Point 3

# Slide 2:
- Point 1
- Point 2
- Point 3

... and so on.
```

Instructions:



""",

    "GET_SLIDE_PROMPT":
    """
Based on the outline and the context provided, give me the contents for the a slide and the speaker notes for the corresponding slide.
The slide should have slide header, slide content, and speaker notes.
The slide should cover the minimum content that can be covered in a slide. Do not have too much content on a single slide.
At least one slide should contain a mermaid diagram compulsorily.
Use diagrams wherever possible.
If there are diagrams or images on a slide, there should not be any other text on the slide.


Slide Header Instructions:
The headers should not be long and appropriate for the content on the slide.  

Slide Content Instructions:
1. Summarize the content in 4-5 bullet points only.
2. Give me the output in the given example Markdown format only.  
3. Bullet points should compulsorily begin with a *.  


Example output markdown format for slide content:  
```markdown
* In a point, here's an [URL to example](https://www.example.com). This explains why this url is important.
* One  
    * One A focuses on **this** point that speaks about the importance of this point that is highlighted in bold.
    * One B has this **important point** that is crucial for understanding the content. All the highlighted points should be in bold.
* Two is the second point that is important for the content.
* Three is the third point that is important for the content.
```

Speaker Notes Instructions:
You are given the content for a slide in a module and the context of the content. You need to create speaker notes for the slide only based on the slide content.
The speaker notes should be in a neutral tone with a continuous flow.  
Do not expand acronyms in the speaker notes.
Do not have any opening remarks like hello, welcome or ending remarks like thank you in the speaker notes.  
Do not return anything other than the output string.  
Speak in continuation as if you were continuing from the previous slide. Do not use comments like 'welcome', 'today, we will discuss', 'in this slide', 'this slide discusses', etc. in the speaker notes.  
For formulae, do not use latex content, instead use words appropriate for the formulae so that they can be converted to audio.

Outline for the slide:

""",
    "BREAK_OUTLINE_PROMPT": """
You are given an outline for a presentation. You need to break down the outline into individual slides.
Each slide should have a slide header and slide content.

Instructions:
1. Each slide should have a slide header and slide content.
2. Return the slide headers and slide content in the given example in json format of list of strings.
3. Do not have anything other than the slide headers and slide content in the output.
4. Multiple lines in the output should be separated by a newline character.

Example:
Input:
# Module 1: Introduction to AI in Finance
## Slide 1: AI in Financial Report Writing
- AI-powered tools for automatic generation of financial reports, quarterly earnings, and forecasts
- AI in Financial Report Writing
- How NLP models can automate content such as market commentary, regulatory documents, or credit analysis
- Example: BloombergGPT for producing financial summaries and analyses


## Slide 2: Natural Language Processing (NLP) in Finance
- How NLP models can automate content such as market commentary, regulatory documents, or credit analysis
- Example: JP Morgan's AI applications in creating research reports


Output:
["AI in Financial Report Writing

AI-powered tools for automatic generation of financial reports, quarterly earnings, and forecasts

AI in Financial Report Writing

How NLP models can automate content such as market commentary, regulatory documents, or credit analysis

Example: BloombergGPT for producing financial summaries and analyses",
"Natural Language Processing (NLP) in Finance

How NLP models can automate content such as market commentary, regulatory documents, or credit analysis

Example: JP Morgan's AI applications in creating research reports"]

Input:


""",

    "GET_MODULE_INFORMATION_PROMPT": """
Given the outline of a slide deck, you need to write the module information for the course.
It should cover what the module will cover.
The output should be in one paragraph and 3-5 or more bullet points.
Do not return anything other than the output string.

Example:
Input:
[{{"slide_header": "AI in Financial Report Writing - AI-powered tools for automatic generation of financial reports, quarterly earnings, and forecasts"}},
{{"slide_header": "Natural Language Processing (NLP) in Finance - How NLP models can automate content such as market commentary, regulatory documents, or credit analysis"}},
{{"slide_header": "Generative AI for Marketing and Client Engagement - Personalized content marketing and customer engagement at scale"}}]

Output:
The module will cover AI in Financial Report Writing, Natural Language Processing (NLP) in Finance, and Generative AI for Marketing and Client Engagement.
- AI-powered tools for automatic generation of financial reports, quarterly earnings, and forecasts
- How NLP models can automate content such as market commentary, regulatory documents, or credit analysis
- Personalized content marketing and customer engagement at scale

Input:

""",


"STREAMLIT_APP_PROMPT": """Given a technical specification document for a Streamlit application, generate the Streamlit code for the application.
The lab should be self suffiecient and should not depend on any outside environment variables, datasets, apis which require environment files or other parameters that are not provided on the current page. If you require these, initialize them in the application itself, otherwise the application will break.
Do not generate incomplete code, or empty blocks of code to be filled by the user. Generate complete code.
Incorporate explanations for code functionalities within the application interface. 
Provide comprehensive explanations to users about visualizations, data, crucial steps, and formulas. 
Ensure the application is interactive, allowing users to visualize real-time changes in input. 
Include an array of graphs, images, charts, and other visualizations to enhance interactivity.


# Output Format

Enclose the generated Streamlit code within Python code blocks.

```python

import streamlit as st

st.set_page_config(page_title="QuLab", layout="wide")
st.sidebar.image("https://www.quantuniversity.com/assets/img/logo5.jpg")
st.sidebar.divider()
st.title("QuLab")
st.divider()

# Code goes here

st.divider()
st.write("© 2025 QuantUniversity. All Rights Reserved.")
st.caption("The purpose of this demonstration is solely for educational use and illustration. "
           "Any reproduction of this demonstration "
           "requires prior written consent from QuantUniversity.")
```

# Notes

- Ensure the generated code is directly executable within a Streamlit environment.
- Balance the complexity of the visualizations with performance to avoid lag.
- Use clear and descriptive comments in the code to maintain clarity, even though the explanation is provided within the app.
- Consider edge cases and inputs that may cause unexpected behavior during real-time updates.

Technical Specification Document:
{TECH_SPEC}
""",

"REQUIREMENTS_FILE_PROMPT": """
Extract the required packages from the given Streamlit application and generate a requirements file.

Return only the requirements file. This response will be used directly to generate and execute the requirements file, so include no other comments or information.

# Notes

- If versions are not specified in the Streamlit application, you may leave them out or assume the latest stable versions. Check for any in-code comments or documentation that might specify particular versions.

# Output Format

Output must be enclosed within three backticks to ensure proper formatting as a text file:
```requirements
```

# Examples

**Given Streamlit application:**

```python
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Some functionalities
```

**Output:**

```
streamlit
pandas
numpy
matplotlib
```

Given Streamlit application:
{STREAMLIT_APP}""",

"README_FILE_PROMPT": """
Generate a README file for the Streamlit application based on the provided technical specification document.

The README file should include the following sections:
- Project Title
- Description
- Installation
- Usage
- Credits
- License

Ensure that the README file is comprehensive and provides clear instructions for installation and usage. Include any necessary details to run the Streamlit application successfully.

# Output Format

Enclose the generated README file within three backticks to ensure proper formatting as a text file:
```markdown
```

{STREAMLIT_APP}
""",

"GET_CODELAB_PROMPT": """
Follow the guidelines below to generate a codelab markdown for the attached streamlit application.
The codelab will focus on the functionalities of the application and provide a comprehensive guide for developers to understand the application.
Highlight the importance of the application, the concepts explained, etc in the first step so that the developer gets proper context.
The codelab should be comprehensive and cover all the functionalities of the application.
If required, create architecture diagrams, flowcharts, or any other visual representation to explain the application's working.

Output format:
Enclose the output in three backticks and markdown format.
For Example:
```markdown
```

Guidelines:
Do not have any seperators like ---, *** etc in the codelab.

## Title

The title is a Header 1.

```
# Title of codelab
```

## Steps

A step is declared by putting the step's title in a Header 2. All content
following a step title will be considered part of the step, until the next step
title, or the end of the document.

```
## Codelab Step
```

### Duration

Steps should be marked with the expected duration to complete them. To label a
step with a duration, put "Duration: TIME" by itself on the line directly
following the step title, where TIME is formatted like "hh:mm:ss" (or "mm:ss" if
only one `:` is provided).

```
## Codelab Step
Duration: 1:25
```

### Content

Codelab content may be written in standard Markdown. Some special constructs are
understood:

#### Fenced Code and Language Hints

Code blocks may be declared by placing them between two lines containing just
three backticks (fenced code blocks). The codelab renderer will attempt to
perform syntax highlighting on code blocks, but it is not always effective at
guessing the language to highlight in. Put the name of the code language after
the first fence to explicitly specify which highlighting plan to use.

```go
This block will be highlighted as Go source code.
```

If you'd like to disable syntax highlighting, you can specify the language
hint to "console":

```console
This block will not be syntax highlighted.
```

#### Info Boxes

Info boxes are colored callouts that enclose special information in codelabs.
Positive info boxes should contain positive information like best practices and
time-saving tips. Negative infoboxes should contain information like warnings
and API usage restriction. If you want to highlight important information, use the <b> tag inside the aside tag.

```
<aside class="positive">
This will appear in a <b>positive</b> info box.
</aside>

<aside class="negative">
This will appear in a <b>negative</b> info box.
</aside>
```

#### Download Buttons

Codelabs sometimes contain links to SDKs or sample code. The codelab renderer
will apply special button-esque styling to any link that begins with the word
"Download".

```
<button>
  [Download SDK](https://www.google.com)
</button>
```


Streamlit Application: 

{STREAMLIT_CODE}
""",

"GET_USER_GUIDE_PROMPT": """
Follow the guidelines below to generate a codelab user guide markdown for the attached streamlit application.
The codelab will focus on the functionalities of the application and provide a comprehensive guide for users to understand how to use the application.
Highlight the importance of the application, the concepts explained, etc in the first step so that the user gets proper context.
The user guide should take the user step by step to understand the working of the application, but should not focus on the code, but the concepts and how the application works to explain the concepts.
The user guide should not be technical unless the application itself is technical (for example, if the codelab is about usage of numpy, it can and must have technical aspects to it).

Output format:
Enclose the output in three backticks and markdown format.
For Example:
```markdown
```

Guidelines:
Do not have any seperators like ---, *** etc in the codelab.

## Title

The title is a Header 1.

```
# Title of codelab
```

## Steps

A step is declared by putting the step's title in a Header 2. All content
following a step title will be considered part of the step, until the next step
title, or the end of the document.

```
## Codelab Step
```

### Duration

Steps should be marked with the expected duration to complete them. To label a
step with a duration, put "Duration: TIME" by itself on the line directly
following the step title, where TIME is formatted like "hh:mm:ss" (or "mm:ss" if
only one `:` is provided).

```
## Codelab Step
Duration: 1:25
```

#### Fenced Code and Language Hints

Code blocks may be declared by placing them between two lines containing just
three backticks (fenced code blocks). The codelab renderer will attempt to
perform syntax highlighting on code blocks, but it is not always effective at
guessing the language to highlight in. Put the name of the code language after
the first fence to explicitly specify which highlighting plan to use.

```go
This block will be highlighted as Go source code.
```

If you'd like to disable syntax highlighting, you can specify the language
hint to "console":

```console
This block will not be syntax highlighted.
```

#### Info Boxes

Info boxes are colored callouts that enclose special information in codelabs.
Positive info boxes should contain positive information like best practices and
time-saving tips. Negative infoboxes should contain information like warnings
and API usage restriction. If you want to highlight important information, use the <b> tag inside the aside tag.

```
<aside class="positive">
This will appear in a <b>positive</b> info box.
</aside>

<aside class="negative">
This will appear in a <b>negative</b> info box.
</aside>
```

```


Streamlit Application: 

{STREAMLIT_CODE}
""",

"GENERATE_LAB_PROMPT": """"
Task:
Create a Streamlit application for the lab "{LAB_NAME}" with the given technical specifications.

Instructions:
1. There SHOULD be an app.py file in the root directory of the repository. 
Create a multi-page application for ease of maintainence and development. 
Compulsorily have multiple pages in multiple files for different functionalities. You can have as many files/directories as you need.
1.1. The main app.py for the streamlit application should enclose the code in the following codeblock:
```python

import streamlit as st

st.set_page_config(page_title="QuLab", layout="wide")
st.sidebar.image("https://www.quantuniversity.com/assets/img/logo5.jpg")
st.sidebar.divider()
st.title("QuLab")
st.divider()

# Your code goes here

st.divider()
st.write("© 2025 QuantUniversity. All Rights Reserved.")
st.caption("The purpose of this demonstration is solely for educational use and illustration. "
           "Any reproduction of this demonstration "
           "requires prior written consent from QuantUniversity.")
```

2. Provide comprehensive explanations to users through markdown about visualizations, data, crucial steps, and formulas. 
Ensure the application is interactive, allowing users to visualize real-time changes in input. 
Include an array of graphs, images, charts, and other visualizations to enhance interactivity. (Use plotly instead of matplotlib for visualizations)
5. COMPULSORILY add the (modified) dockerfile, requirements.txt, app.py and README.md and other generated files to the repository using the write_file_to_github tool. The tool requires complete working code.
6. Validate the generated code before writing it to github for red flags (e.g. destructive commands, suspicious imports, sensitive information, etc.) and write them in markdown on the frontend.


Technical Specifications:
```
{TECH_SPEC}
```

Dockerfile:
```
{DOCKERFILE}
```
""",
}


def get_prompts():
    return prompts

