#!/usr/bin/env python3
'''Video generation via Google Veo 3 API with fallback.'''
import os, time, logging, requests
logger = logging.getLogger('pipeline.video')

FALLBACK_VIDEOS = [
    'https://assets.mixkit.co/videos/preview/mixkit-futuristic-control-room-interface-41617-large.mp4',
    'https://assets.mixkit.co/videos/preview/mixkit-space-shuttle-launching-in-space-32128-large.mp4',
    'https://assets.mixkit.co/videos/preview/mixkit-desert-canyon-with-sunlight-effects-43288-large.mp4',
    'https://assets.mixkit.co/videos/preview/mixkit-woman-working-at-a-office-desk-40810-large.mp4',
    'https://assets.mixkit.co/videos/preview/mixkit-hand-holding-a-smartphone-with-a-blank-screen-40742-large.mp4'
]

def generate_scenes(scenes, style, aspect_ratio, output_dir, veo_key, job_id):
    '''Generate video for each scene using Veo 3 API.'''
    scene_videos = []

    for i, scene in enumerate(scenes):
        logger.info(f'[{job_id}] Generating video for scene {i+1}/{len(scenes)}: {scene.get(" title\, \Scene\)}')
 logger.info(f'[{job_id}] Generating video for scene {i+1}/{len(scenes)}: {scene.get("title", f"Scene {i+1}")}')

 if veo_key:
 video_path = _generate_veo3(scene, aspect_ratio, output_dir, veo_key, job_id, i)

 if not video_path:
 logger.warning(f'[{job_id}] Scene {i+1}: Using fallback video')
 video_path = _download_fallback(output_dir, i)

 scene_videos.append({
 'sceneNum': scene.get('sceneNum', i+1),
 'title': scene.get('title', f'Scene {i+1}'),
 'videoPath': video_path,
 'duration': scene.get('duration', 20),
 'voiceText': scene.get('voiceText', '')
 })

 return scene_videos

def _generate_veo3(scene, aspect_ratio, output_dir, veo_key, job_id, idx):
 '''Submit Veo 3 generation and poll for result.'''
 prompt = scene.get('videoPrompt', scene.get('scriptText', ''))
 if not prompt:
 return None

 endpoint = f'https://generativelanguage.googleapis.com/v1beta/models/veo-3.0-generate-preview:predictLongRunning?key={veo_key}'

 try:
 resp = requests.post(endpoint, json={
 'instances': [{'prompt': prompt}],
 'parameters': {
 'aspectRatio': aspect_ratio or '16:9',
 'durationSeconds': '8',
 'personGeneration': 'allow_adult',
 'sampleCount': 1,
 'addWatermark': False
 }
 }, timeout=30)

 if not resp.ok:
 logger.warning(f'[{job_id}] Veo 3 scene {idx+1} submission failed: {resp.status_code} {resp.text[:200]}')
 return None

 op = resp.json().get('name', '')
 if not op:
 return None

 logger.info(f'[{job_id}] Veo 3 operation started: {op}')

 # Poll for result (max 10 min)
 poll_url = f'https://generativelanguage.googleapis.com/v1beta/{op}?key={veo_key}'
 for attempt in range(150):
 time.sleep(4)
 poll_resp = requests.get(poll_url, timeout=15)
 if not poll_resp.ok:
 continue
 poll_data = poll_resp.json()
 if poll_data.get('done'):
 samples = poll_data.get('response', {}).get('generateVideoResponse', {}).get('generatedSamples', [])
 video_uri = samples[0].get('video', {}).get('uri', '') if samples else ''
 if video_uri:
 # Download video
 video_path = os.path.join(output_dir, f'scene_{idx+1}_veo3.mp4')
 dl = requests.get(video_uri, timeout=120, headers={'Authorization': f'Bearer {veo_key}'})
 if dl.ok:
 with open(video_path, 'wb') as f:
 f.write(dl.content)
 logger.info(f'[{job_id}] Scene {idx+1} downloaded: {video_path}')
 return video_path
 break

 except Exception as e:
 logger.error(f'[{job_id}] Veo 3 error for scene {idx+1}: {e}')

 return None

def _download_fallback(output_dir, idx):
 '''Download a fallback stock video.'''
 url = FALLBACK_VIDEOS[idx % len(FALLBACK_VIDEOS)]
 video_path = os.path.join(output_dir, f'scene_{idx+1}_fallback.mp4')
 try:
 resp = requests.get(url, timeout=30, stream=True)
 if resp.ok:
 with open(video_path, 'wb') as f:
 for chunk in resp.iter_content(chunk_size=65536):
 f.write(chunk)
 return video_path
 except Exception as e:
 logger.error(f'Fallback video download failed: {e}')
 return None
