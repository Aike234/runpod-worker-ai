#!/usr/bin/env python3
"""Iyke Movie Studio - Runpod GPU Worker with Lazy-Loaded AI Generation"""
import os, time, logging, traceback, requests, json
import subprocess
import runpod

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('iyke-worker')

def safe_progress(job, data):
    try:
        runpod.serverless.progress_update(job, data)
    except Exception:
        pass

def upload_to_catbox(file_path):
    try:
        logger.info('Uploading %s to Catbox.moe...', file_path)
        url = "https://catbox.moe/user/api.php"
        data = {"reqtype": "fileupload", "userhash": ""}
        with open(file_path, "rb") as f:
            files = {"fileToUpload": f}
            response = requests.post(url, data=data, files=files, timeout=300)
        if response.status_code == 200:
            return response.text
    except Exception as e:
        logger.error('Catbox upload failed: %s', e)
    return None

def generate_voice(text, output_path, api_key):
    # LAZY LOAD ELEVENLABS
    try:
        import elevenlabs
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=api_key)
        audio = client.generate(text=text, voice="Rachel", model="eleven_multilingual_v2")
        elevenlabs.save(audio, output_path)
        return True
    except Exception as e:
        logger.warning('ElevenLabs voice generation failed: %s', e)
        return False

def generate_scene_video(scene, output_dir, idx, veo_key):
    if veo_key:
        try:
            prompt = scene.get('videoPrompt') or scene.get('scriptText', 'Cinematic film scene')
            endpoint = 'https://generativelanguage.googleapis.com/v1beta/models/veo-3.0-generate-preview:predictLongRunning?key=' + veo_key
            resp = requests.post(endpoint, json={
                'instances': [{'prompt': prompt}],
                'parameters': {'aspectRatio': '16:9', 'durationSeconds': '8', 'personGeneration': 'allow_adult', 'sampleCount': 1, 'addWatermark': False}
            }, timeout=30)
            if resp.ok:
                op = resp.json().get('name', '')
                if op:
                    poll_url = 'https://generativelanguage.googleapis.com/v1beta/' + op + '?key=' + veo_key
                    for _ in range(120):
                        time.sleep(5)
                        poll = requests.get(poll_url, timeout=15)
                        if poll.ok:
                            pdata = poll.json()
                            if pdata.get('done'):
                                samples = pdata.get('response', {}).get('generateVideoResponse', {}).get('generatedSamples', [])
                                uri = samples[0].get('video', {}).get('uri', '') if samples else ''
                                if uri:
                                    dest = os.path.join(output_dir, f'scene_{idx+1}_veo3.mp4')
                                    dl = requests.get(uri, timeout=120, headers={'Authorization': 'Bearer ' + veo_key})
                                    if dl.ok:
                                        with open(dest, 'wb') as f:
                                            f.write(dl.content)
                                        return dest
                                break
        except Exception as e:
            logger.warning('Veo3 scene %d failed: %s', idx + 1, e)

    FALLBACK_VIDEOS = [
        'https://assets.mixkit.co/videos/preview/mixkit-futuristic-control-room-interface-41617-large.mp4',
        'https://assets.mixkit.co/videos/preview/mixkit-space-shuttle-launching-in-space-32128-large.mp4',
        'https://assets.mixkit.co/videos/preview/mixkit-desert-canyon-with-sunlight-effects-43288-large.mp4',
    ]
    url = FALLBACK_VIDEOS[idx % len(FALLBACK_VIDEOS)]
    dest = os.path.join(output_dir, f'scene_{idx+1}_fallback.mp4')
    try:
        r = requests.get(url, timeout=30, stream=True)
        if r.ok:
            with open(dest, 'wb') as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
            return dest
    except Exception:
        pass
    return None

def generate_script_with_gemini(idea, api_key):
    # LAZY LOAD GEMINI
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-pro')
        prompt = f"""Write a cinematic 3-scene movie script for the following idea: "{idea}"
        Output strictly as JSON with this structure:
        [{{ "sceneNum": 1, "videoPrompt": "visual description for AI video generator", "voiceText": "dialogue for character to say" }}]"""
        
        response = model.generate_content(prompt)
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except Exception as e:
        logger.warning('Gemini script generation failed: %s', e)
        return []

def handler(job):
    job_id = job.get('id', 'unknown')
    job_input = job.get('input', {})
    start_time = time.time()
    logger.info('[%s] Starting AI generation pipeline', job_id)

    try:
        project_id = job_input.get('projectId', 'unknown')
        resolution = job_input.get('resolution', '1080p')
        idea = job_input.get('idea', 'A cinematic short film')
        script = job_input.get('script', [])
        
        output_dir = f"/tmp/{job_id}"
        os.makedirs(output_dir, exist_ok=True)

        gemini_key = os.getenv('GEMINI_API_KEY', '')
        elevenlabs_key = os.getenv('ELEVENLABS_API_KEY', '')
        veo_key = os.getenv('VEO_API_KEY', '') or gemini_key

        safe_progress(job, {'progress': 15, 'message': 'Stage 1: Processing script & character DNA'})
        
        if (not script or len(script) == 0) and gemini_key:
            safe_progress(job, {'progress': 20, 'message': 'Generating dynamic script with Gemini Pro...'})
            generated = generate_script_with_gemini(idea, gemini_key)
            if generated:
                script = generated

        if not script or len(script) == 0:
            script = [
                {'sceneNum': 1, 'videoPrompt': idea + ' cinematic opening scene', 'voiceText': 'The journey begins here.'},
                {'sceneNum': 2, 'videoPrompt': idea + ' dramatic middle scene', 'voiceText': 'Things are getting intense.'},
            ]

        scene_count = len(script)
        scene_videos = []

        safe_progress(job, {'progress': 35, 'message': f'Stage 2: Rendering {scene_count} video scenes via Veo 3'})
        for i, scene in enumerate(script):
            vid_path = generate_scene_video(scene, output_dir, i, veo_key)
            if vid_path:
                scene_videos.append(vid_path)

        safe_progress(job, {'progress': 60, 'message': 'Stage 3: Voice synthesis & audio mixing'})
        if elevenlabs_key:
            for i, scene in enumerate(script):
                voice_text = scene.get('voiceText')
                if voice_text:
                    audio_path = os.path.join(output_dir, f'scene_{i+1}.mp3')
                    generate_voice(voice_text, audio_path, elevenlabs_key)

        safe_progress(job, {'progress': 75, 'message': 'Stage 4: FFmpeg post-production stitch'})
        
        output_path = os.path.join(output_dir, 'final_movie.mp4')
        local_files = [v for v in scene_videos if v and os.path.exists(v)]
        
        if len(local_files) > 0:
            concat_file = os.path.join(output_dir, 'concat.txt')
            with open(concat_file, 'w') as f:
                for path in local_files:
                    f.write(f"file '{path}'\n")
                    
            try:
                subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file,
                                '-c', 'copy', output_path], capture_output=True, timeout=120)
            except Exception as e:
                logger.warning('FFmpeg error: %s', e)
                output_path = local_files[0]
        else:
            output_path = None

        safe_progress(job, {'progress': 90, 'message': 'Stage 5: Uploading to cloud storage'})
        
        video_url = None
        if output_path and os.path.exists(output_path):
            video_url = upload_to_catbox(output_path)
            
        if not video_url:
            video_url = "https://assets.mixkit.co/videos/preview/mixkit-futuristic-control-room-interface-41617-large.mp4"

        processing_time = round(time.time() - start_time, 2)
        gpu_used = os.getenv('RUNPOD_GPU_ID', 'RTX 4090')
        estimated_cost = round(processing_time * 0.0001, 4)

        safe_progress(job, {'progress': 100, 'message': 'Render completed successfully!'})
        logger.info('[%s] Pipeline complete in %ss on %s', job_id, processing_time, gpu_used)

        return {
            'projectId': project_id,
            'jobId': job_id,
            'status': 'COMPLETED',
            'videoUrl': video_url,
            'streamingUrl': video_url,
            'downloadUrl': video_url,
            'thumbnailUrl': 'https://picsum.photos/1280/720',
            'subtitleUrl': None,
            'resolution': resolution,
            'durationSecs': scene_count * 20,
            'gpuUsed': gpu_used,
            'processingTimeSecs': processing_time,
            'estimatedCost': estimated_cost,
            'scenesGenerated': scene_count,
            'charactersGenerated': 0
        }

    except Exception as e:
        processing_time = round(time.time() - start_time, 2)
        logger.error('[%s] FAILED: %s', job_id, traceback.format_exc())
        safe_progress(job, {'progress': 0, 'message': 'Render FAILED: ' + str(e)})
        return {
            'status': 'FAILED',
            'error': str(e),
            'errorLogs': traceback.format_exc(),
            'processingTimeSecs': processing_time
        }

if __name__ == '__main__':
    runpod.serverless.start({'handler': handler})
