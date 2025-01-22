from PIL import Image, ImageDraw, ImageFont
from textwrap import wrap
import os

course_name = "Fundamental Principles of Value"
certificate = Image.open(open("./dags/course/assets/QU-Certificate.jpg", "rb"))
module_id = "1234"
