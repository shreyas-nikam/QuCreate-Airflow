import vimeo
import os
from dotenv import load_dotenv
import time
import logging

module_name="P/E Ratio"
load_dotenv()

video_path = 'uploaded_video.mp4'

print(f"Uploading video to vimeo: {video_path}")
vimeo_client = vimeo.VimeoClient(
    token=os.getenv("VIMEO_ACCESS_TOKEN"),
    key=os.getenv("VIMEO_CLIENT_ID"),
    secret=os.getenv("VIMEO_CLIENT_SECRET")
)
uri = vimeo_client.upload(video_path, data={
    'name': module_name,
    'description': 'AI Generated video for the module.',
    'privacy': {
        'view': 'anybody'
    }
})

print("URI: ", uri)

response = "pending"
video_link = ""
while True:
    response = vimeo_client.get(uri + '?fields=transcode.status').json()
    if response['transcode']['status'] == 'complete':
        print("Video uploaded successfully")
        video_link = vimeo_client.get(uri+"?fields=link").json()
        print(video_link)
        video_link = video_link['link']
        break
    else:
        print("Video upload is still pending")
        time.sleep(5)

video_id = uri.split("/")[-1]

print(video_link)

print


# embed_link = f"""<div style="padding:56.25% 0 0 0;position:relative;"><iframe src="https://player.vimeo.com/video/1051982199?badge=0&amp;autopause=0&amp;player_id=0&amp;app_id=58479" frameborder="0" allow="autoplay; fullscreen; picture-in-picture; clipboard-write; encrypted-media" style="position:absolute;top:0;left:0;width:100%;height:100%;" title="Fundamental Principles of Value Creation"></iframe></div><script src="https://player.vimeo.com/api/player.js"></script>"""
# print()
# print(embed_link)