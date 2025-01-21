import vimeo

# Replace these with your actual credentials
access_token = '0dfed8155bbbe50bb361aa5b41d01f85'
client_id = 'b6d68cc72c59770fccf5e9d75e8d557d20b18a5b'
client_secret = 'EtQCDyR0JfxErxc25B/G08gI4rT7yoR3h2M+W38TaE7BazzDVUubtS7WOWeqjX+3u/MKYWV/dFZXLRde5VunFFV4KGzeHvHdkEGG+BsbPKCh6kPQJ5V3cbuOlfcPn+ip'

# Initialize the Vimeo client
client = vimeo.VimeoClient(
    token=access_token,
    key=client_id,
    secret=client_secret
)

# Path to your video file
video_file_path = 'video.mp4'

try:
    # Upload the video
    uri = client.upload(video_file_path)
    print(f"Video uploaded successfully. URI: {uri}")

    # Retrieve video metadata
    video_data = client.get(uri + '?fields=link').json()
    video_link = video_data['link']
    print(f"Video link: {video_link}")

    # Construct the embed link
    video_id = video_link.split('/')[-1]
    embed_link = f"https://player.vimeo.com/video/{video_id}"
    print(f"Embed link: {embed_link}")

except vimeo.exceptions.VideoUploadFailure as e:
    print(f"Error uploading video: {e}")
