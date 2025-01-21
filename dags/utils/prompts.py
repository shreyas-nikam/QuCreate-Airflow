
prompts = {
   
"CONTENT_TO_QUESTIONS_PROMPT": """
You are given the content for a module. You need to create {NUM_QUESTIONS} questions from the content.
Each question object should have the following keys: "question", "options", "answer_option", and "explanation".
All questions should have at least 4 options and the answer must be in one of the options.
Do not return anything other than the output json.

Instructions:
The questions must be comprehensive and not superficial.
The explanations should be detailed.
The questions should focus on the important points in each part.


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

"GET_MD_CONTENT_PROMPT":"""
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

"COURSE_OUTLINE_TO_DF_PROMPT":"""
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

"GET_RESEARCH_CONTENT_PROMPT":"""
I am working on the module {MODULE_NAME} and I need detailed research notes on the topic {TOPIC_NAME}. 
Please provide an in-depth explanation that includes key concepts, theories, examples, links to images, links to diagrams, and any important studies or data related to the topic. 
Organize the notes in a clear and structured way, with headings and subheadings if necessary. Make sure the notes are suitable for academic research, including any relevant citations or references to major works in this area.
""",

"GET_OUTLINE_PROMPT":"""
You are creating an outline for a presentation for a course. 
For all the material that is uploaded, create an outline based on the user's instructions.
The outline should be structured and organized in a logical flow.
The outline can have interleaved text and images.
The outline should have a header, bullet points, and image links in markdown format.
Since you cannot directly produce an image, the image block takes in a file path - you should write in the file path of the image instead.
How do you know which image to generate? Each context chunk will contain metadata including an image render of the source chunk, given as a file path. 
Include ONLY the images from the chunks that have heavy visual elements (you can get a hint of this if the parsed text contains a lot of tables).
You MUST include at least one image block in the output.

Output format:
```markdown
# Module 1: Introduction to AI in Finance

- Topic 1: AI in Financial Report Writing
- Topic 2: Natural Language Processing (NLP) in Finance
- Topic 3: Generative AI for Marketing and Client Engagement

![Image Description in detail for speaker notes](path/to/image.jpg)

# Module 2: AI in Financial Risk Management

- Topic 1: Predictive Analytics for Risk Assessment
- Topic 2: AI in Fraud Detection and Prevention
- Topic 3: Automated Compliance Monitoring
- Topic 4: AI in Fraud Detection and Prevention

... and so on.
```

Instructions:



""",

"GET_SLIDE_PROMPT":
"""
Based on the outline and the context provided, give me the contents for the a slide and the speaker notes for the corresponding slide.
The slide should have slide header, slide content, and speaker notes.

Slide Header Instructions:
The headers should not be long and appropriate for the content on the slide.  

Slide Content Instructions:
1. Summarize the content in 4-5 bullet points only.
2. Give me the output in the given example Markdown format only.  
3. Bullet points should compulsorily begin with a *.  
4. Do not have any headers with less than 3 bullet points.


Example output markdown format for slide content:  
```markdown

* In a point, here's an [URL to example](https://www.example.com). This explains why this url is important.
* One  
    * One A focuses on **this** point that speaks about the importance of this point that is highlighted in bold.
    * One B has this **important point** that is crucial for understanding the content. All the highlighted points should be in bold.
* Two is the second point that is important for the content.
* Three is the third point that is important for the content.

Speaker Notes Instructions:
1. The speaker notes should be in a neutral tone with a continuous flow.  
2. Do not expand acronyms in the speaker notes.
3. Do not have any opening remarks like hello, welcome or ending remarks like thank you in the speaker notes.  
4. Do not return anything other than the output string.  
5. Speak in continuation as if you were continuing from the previous slide. Do not use comments like 'today, we will discuss', 'in this slide', 'this slide discusses', etc. in the speaker notes.  
6. For formulae, do not use latex content, instead use words appropriate for the formulae so that they can be converted to audio. 


Outline for the slide:

"""

}

def get_prompts():
	return prompts