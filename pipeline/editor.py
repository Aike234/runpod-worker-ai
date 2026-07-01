#!/usr/bin/env python3
'''FFmpeg video editing: stitch, upscale, subtitle burn, thumbnail.'''
import os, subprocess, logging, json, time
logger = logging.getLogger('pipeline.editor')

RESOLUTION_MAP = {'720p': '1280:720', '1080p': '1920:1080', '4K': '3840:2160', '2K': '2560:1440'}

def stitch_and_edit(scene_videos, voice_tracks, screenplay, output_dir, resolution, aspect_ratio, add_subtitles, title, job_id):
    '''Stitch scenes, add audio, upscale, burn subtitles, generate thumbnail.'''
    logger.info(f'[{job_id}] Starting FFmpeg editing pipeline')
    os.makedirs(output_dir, exist_ok=True)

    # Filter valid scene videos
    valid_scenes = [s for s in scene_videos if s.get('videoPath') and os.path.exists(s['videoPath'])]
    if not valid_scenes:
        logger.error(f'[{job_id}] No valid scene videos to edit')
        return {'error': 'No valid scene videos'}

    # 1. Merge voice with video per scene
    merged_scenes = []
    for i, scene in enumerate(valid_scenes):
        merged_path = _merge_audio_video(
            video_path=scene['videoPath'],
            audio_path=voice_tracks[i] if i < len(voice_tracks) and voice_tracks else None,
            output_dir=output_dir,
            scene_idx=i,
            job_id=job_id
        )
        merged_scenes.append(merged_path or scene['videoPath'])

    # 2. Concatenate all scenes
    concat_path = os.path.join(output_dir, 'concat_raw.mp4')
    _concat_videos(merged_scenes, concat_path, job_id)

    # 3. Upscale to target resolution
    target_res = RESOLUTION_MAP.get(resolution, '1920:1080')
    upscaled_path = os.path.join(output_dir, f'movie_{resolution}.mp4')
    _upscale_video(concat_path, upscaled_path, target_res, job_id)

    # 4. Generate SRT subtitles and burn them
    subtitle_path = None
    final_path = upscaled_path
    if add_subtitles and screenplay:
        subtitle_path = _generate_srt(screenplay, output_dir, job_id)
        if subtitle_path:
            subtitled_path = os.path.join(output_dir, f'movie_{resolution}_subtitled.mp4')
            _burn_subtitles(upscaled_path, subtitle_path, subtitled_path, job_id)
            if os.path.exists(subtitled_path):
                final_path = subtitled_path

    # 5. Generate thumbnail (frame at 2s)
    thumbnail_path = _generate_thumbnail(final_path, output_dir, job_id)

    # Get duration
    duration_secs = _get_duration(final_path)
    logger.info(f'[{job_id}] Edit complete. Output: {final_path} ({duration_secs:.1f}s)')

    return {
        'videoPath': final_path,
        'subtitlePath': subtitle_path,
        'thumbnailPath': thumbnail_path,
        'duration_secs': duration_secs,
        'resolution': resolution
    }

def _merge_audio_video(video_path, audio_path, output_dir, scene_idx, job_id):
    out = os.path.join(output_dir, f'scene_{scene_idx+1}_merged.mp4')
    if audio_path and os.path.exists(audio_path):
        cmd = ['ffmpeg', '-y', '-i', video_path, '-i', audio_path, '-c:v', 'copy', '-c:a', 'aac', '-shortest', out]
    else:
        cmd = ['ffmpeg', '-y', '-i', video_path, '-c', 'copy', out]
    _run_ffmpeg(cmd, job_id)
    return out if os.path.exists(out) else None

def _concat_videos(video_paths, output_path, job_id):
    list_file = output_path + '_list.txt'
    with open(list_file, 'w') as f:
        for p in video_paths:
            f.write(f" file {p} \n\)
 cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', list_file, '-c', 'copy', output_path]
 _run_ffmpeg(cmd, job_id)

def _upscale_video(input_path, output_path, resolution, job_id):
 cmd = ['ffmpeg', '-y', '-i', input_path, '-vf', f'scale={resolution}:flags=lanczos', '-c:v', 'libx264', '-crf', '18', '-preset', 'slow', '-c:a', 'copy', output_path]
 _run_ffmpeg(cmd, job_id)

def _generate_srt(screenplay, output_dir, job_id):
 srt_path = os.path.join(output_dir, 'subtitles.srt')
 current_time = 0
 with open(srt_path, 'w', encoding='utf-8') as f:
 for i, scene in enumerate(screenplay):
 voice_text = scene.get('voiceText', '').strip()
 duration = scene.get('duration', 20)
 if voice_text:
 start = _sec_to_srt(current_time)
 end = _sec_to_srt(current_time + duration)
 f.write(f'{i+1}\n{start} --> {end}\n{voice_text}\n\n')
 current_time += duration
 return srt_path

def _burn_subtitles(input_path, srt_path, output_path, job_id):
 srt_escaped = srt_path.replace('\\\\', '/').replace(':', '\\\\:')
 cmd = ['ffmpeg', '-y', '-i', input_path, '-vf', f\subtitles={srt_path}:force_style=FontSize=24,FontName=Arial,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2\, '-c:a', 'copy', output_path]
 _run_ffmpeg(cmd, job_id)

def _generate_thumbnail(video_path, output_dir, job_id):
 thumb_path = os.path.join(output_dir, 'thumbnail.jpg')
 cmd = ['ffmpeg', '-y', '-i', video_path, '-ss', '00:00:02', '-vframes', '1', '-q:v', '2', '-vf', 'scale=1280:720', thumb_path]
 _run_ffmpeg(cmd, job_id)
 return thumb_path if os.path.exists(thumb_path) else None

def _get_duration(video_path):
 try:
 result = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', video_path], capture_output=True, text=True, timeout=10)
 return float(result.stdout.strip()) if result.stdout.strip() else 0
 except:
 return 0

def _run_ffmpeg(cmd, job_id):
 try:
 result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
 if result.returncode != 0:
 logger.warning(f'[{job_id}] FFmpeg warning: {result.stderr[-300:]}')
 return result.returncode == 0
 except subprocess.TimeoutExpired:
 logger.error(f'[{job_id}] FFmpeg timed out')
 return False
 except Exception as e:
 logger.error(f'[{job_id}] FFmpeg error: {e}')
 return False

def _sec_to_srt(seconds):
 h = int(seconds // 3600)
 m = int((seconds % 3600) // 60)
 s = int(seconds % 60)
 ms = int((seconds - int(seconds)) * 1000)
 return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'
