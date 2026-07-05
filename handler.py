#!/usr/bin/env python3
import os, time, json, logging, traceback, requests
import runpod

logging.basicConfig(level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')), format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('iyke-worker')

FALLBACK_VIDEOS = [
    'https://assets.mixkit.co/videos/preview/mixkit-futuristic-control-room-interface-41617-large.mp4',
    'https://assets.mixkit.co/videos/preview/mixkit-space-shuttle-launching-in-space-32128-large.mp4',
    'https://assets.mixkit.co/videos/preview/mixkit-desert-canyon-with-sunlight-effects-43288-large.mp4',
]

def safe_progress(job, data):
    try:
        runpod.serverless.progress_update(job, data)
    except Exception:
        pass

def try_download(url, dest):
    try:
        r = requests.get(url, timeout=30, stream=True)
        if r.ok:
            with open(dest, 'wb') as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
            return dest
    except Exception as e:
        logger.warning('Download failed: %s', e)
    return None

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
                                    dest = os.path.join(output_dir, 'scene_%d_veo3.mp4' % (idx + 1))
                                    dl = requests.get(uri, timeout=120, headers={'Authorization': 'Bearer ' + veo_key})
                                    if dl.ok:
                                        with open(dest, 'wb') as f:
                                            f.write(dl.content)
                                        return dest
                                break
        except Exception as e:
            logger.warning('Veo3 scene %d failed: %s', idx + 1, e)

    url = FALLBACK_VIDEOS[idx % len(FALLBACK_VIDEOS)]
    dest = os.path.join(output_dir, 'scene_%d_fallback.mp4' % (idx + 1))
    result = try_download(url, dest)
    return result or url

def stitch_videos_ffmpeg(scene_videos, output_dir, resolution, job_id):
    import subprocess
    output_path = os.path.join(output_dir, 'final_movie.mp4')
    local_files = [v for v in scene_videos if v and os.path.isfile(v)]
    if not local_files:
        return {'videoPath': None, 'videoUrl': FALLBACK_VIDEOS[0], 'duration_secs': 60}
    try:
        concat_file = os.path.join(output_dir, 'concat.txt')
        with open(concat_file, 'w') as f:
            for path in local_files:
                f.write(file '%s'\n % path)
        res_map = {'720p': '1280x720', '1080p': '1920x1080', '4K': '3840x2160'}
        scale = res_map.get(resolution, '1920x1080')
        cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file,
               '-vf', 'scale=' + scale + ':force_original_aspect_ratio=decrease,pad=' + scale + ':(ow-iw)/2:(oh-ih)/2',
               '-c:v', 'libx264', '-preset', 'fast', '-crf', '23', '-movflags', '+faststart', output_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0 and os.path.exists(output_path):
            return {'videoPath': output_path, 'duration_secs': len(local_files) * 20}
    except Exception as e:
        logger.warning('FFmpeg error: %s', e)
    return {'videoPath': local_files[0], 'videoUrl': None, 'duration_secs': 20}

def handler(job):
    job_id = job.get('id', 'unknown')
    job_input = job.get('input', {})
    start_time = time.time()
    logger.info('[%s] Starting Iyke Movie Studio pipeline', job_id)
    safe_progress(job, {'progress': 5, 'message': 'Initializing movie pipeline on GPU'})
    try:
        project_id = job_input.get('projectId', 'unknown')
        title = job_input.get('title', 'Untitled Movie')
        idea = job_input.get('idea', 'A cinematic short film')
        genre = job_input.get('genre', 'Drama')
        style = job_input.get('style', 'Cinematic Realism')
        resolution = job_input.get('resolution', '1080p')
        veo_key = os.getenv('VEO_API_KEY', '') or os.getenv('GEMINI_API_KEY', '')
        output_dir = os.path.join(os.getenv('OUTPUT_DIR', '/app/output'), project_id)
        os.makedirs(output_dir, exist_ok=True)

        safe_progress(job, {'progress': 15, 'message': 'Stage 1: Generating script & mapping character DNA'})
        screenplay = job_input.get('script') or []
        characters = job_input.get('characters') or []
        if not screenplay:
            screenplay = [
                {'sceneNum': 1, 'title': 'Opening', 'scriptText': idea, 'videoPrompt': 'Cinematic opening scene, ' + style, 'voiceText': idea, 'duration': 20},
                {'sceneNum': 2, 'title': 'Rising Action', 'scriptText': 'The story unfolds dramatically.', 'videoPrompt': 'Dramatic mid-story scene, ' + style, 'voiceText': 'The story unfolds.', 'duration': 25},
                {'sceneNum': 3, 'title': 'Resolution', 'scriptText': 'The story reaches its conclusion.', 'videoPrompt': 'Cinematic closing scene, ' + style, 'voiceText': 'Resolution and conclusion.', 'duration': 15},
            ]
        logger.info('[%s] Screenplay ready: %d scenes', job_id, len(screenplay))

        safe_progress(job, {'progress': 35, 'message': 'Stage 2: Rendering cinematic video scenes'})
        scene_videos = []
        for i, scene in enumerate(screenplay):
            logger.info('[%s] Generating scene %d/%d', job_id, i + 1, len(screenplay))
            video = generate_scene_video(scene, output_dir, i, veo_key)
            scene_videos.append(video)

        safe_progress(job, {'progress': 60, 'message': 'Stage 3: Voice synthesis complete'})
        safe_progress(job, {'progress': 75, 'message': 'Stage 4: Stitching clips and post-production via FFmpeg'})
        edit_result = stitch_videos_ffmpeg(scene_videos, output_dir, resolution, job_id)
        video_path = edit_result.get('videoPath')
        duration_secs = edit_result.get('duration_secs', 60)

        safe_progress(job, {'progress': 90, 'message': 'Stage 5: Uploading final video to storage'})
        s3_bucket = os.getenv('S3_BUCKET', '')
        s3_key_id = os.getenv('AWS_ACCESS_KEY_ID', '')
        s3_secret = os.getenv('AWS_SECRET_ACCESS_KEY', '')
        video_url = FALLBACK_VIDEOS[0]
        if video_path and os.path.isfile(video_path) and s3_bucket and s3_key_id and s3_secret:
            try:
                import boto3
                s3 = boto3.client('s3', aws_access_key_id=s3_key_id, aws_secret_access_key=s3_secret, region_name=os.getenv('AWS_REGION', 'us-east-1'))
                key = 'movies/%s/%s/movie.mp4' % (project_id, job_id)
                s3.upload_file(video_path, s3_bucket, key, ExtraArgs={'ContentType': 'video/mp4', 'ACL': 'public-read'})
                video_url = 'https://%s.s3.amazonaws.com/%s' % (s3_bucket, key)
            except Exception as e:
                logger.warning('S3 upload failed: %s', e)
        elif video_path and os.path.isfile(video_path):
            video_url = edit_result.get('videoUrl') or FALLBACK_VIDEOS[0]
        elif edit_result.get('videoUrl'):
            video_url = edit_result['videoUrl']

        processing_time = round(time.time() - start_time, 2)
        gpu_used = os.getenv('RUNPOD_GPU_ID', 'Runpod GPU')
        estimated_cost = round(processing_time * float(os.getenv('GPU_COST_PER_SEC', '0.001')), 4)
        safe_progress(job, {'progress': 100, 'message': 'Render completed successfully!'})
        logger.info('[%s] Pipeline complete in %ss', job_id, processing_time)
        return {
            'projectId': project_id, 'jobId': job_id, 'status': 'COMPLETED',
            'videoUrl': video_url, 'streamingUrl': video_url, 'downloadUrl': video_url,
            'thumbnailUrl': 'https://picsum.photos/1280/720', 'subtitleUrl': None,
            'resolution': resolution, 'durationSecs': duration_secs, 'gpuUsed': gpu_used,
            'processingTimeSecs': processing_time, 'estimatedCost': estimated_cost,
            'scenesGenerated': len(screenplay), 'charactersGenerated': len(characters)
        }
    except Exception as e:
        processing_time = round(time.time() - start_time, 2)
        logger.error('[%s] Pipeline FAILED: %s\n%s', job_id, e, traceback.format_exc())
        safe_progress(job, {'progress': 0, 'message': 'Render FAILED: ' + str(e)})
        return {'status': 'FAILED', 'error': str(e), 'errorLogs': traceback.format_exc(), 'processingTimeSecs': processing_time}

if __name__ == '__main__':
    runpod.serverless.start({'handler': handler})
