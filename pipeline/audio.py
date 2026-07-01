#!/usr/bin/env python3
'''Voice synthesis via ElevenLabs API.'''
import os, logging, requests
logger = logging.getLogger('pipeline.audio')

DEFAULT_VOICE_ID = '21m00Tcm4TlvDq8ikWAM'  # ElevenLabs Rachel voice

def generate_voice(scenes, output_dir, elevenlabs_key, job_id):
    '''Generate voice narration for each scene.'''
    if not elevenlabs_key:
        logger.warning(f'[{job_id}] No ElevenLabs key - skipping voice generation')
        return []

    voice_tracks = []
    for i, scene in enumerate(scenes):
        voice_text = scene.get('voiceText', '').strip()
        if not voice_text:
            voice_tracks.append(None)
            continue

        logger.info(f'[{job_id}] Synthesizing voice for scene {i+1}')
        audio_path = _synthesize(voice_text, output_dir, elevenlabs_key, i, job_id)
        voice_tracks.append(audio_path)

    return voice_tracks

def _synthesize(text, output_dir, api_key, idx, job_id):
    '''Call ElevenLabs TTS API.'''
    voice_id = os.getenv('ELEVENLABS_VOICE_ID', DEFAULT_VOICE_ID)
    url = f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}'

    try:
        resp = requests.post(url, json={
            'text': text,
            'model_id': 'eleven_multilingual_v2',
            'voice_settings': {'stability': 0.5, 'similarity_boost': 0.8, 'style': 0.2}
        }, headers={
            'xi-api-key': api_key,
            'Content-Type': 'application/json',
            'Accept': 'audio/mpeg'
        }, timeout=60)

        if resp.ok:
            audio_path = os.path.join(output_dir, f'voice_scene_{idx+1}.mp3')
            with open(audio_path, 'wb') as f:
                f.write(resp.content)
            logger.info(f'[{job_id}] Voice scene {idx+1} saved: {audio_path}')
            return audio_path
        else:
            logger.warning(f'[{job_id}] ElevenLabs failed scene {idx+1}: {resp.status_code} {resp.text[:100]}')
    except Exception as e:
        logger.error(f'[{job_id}] Voice synthesis error scene {idx+1}: {e}')
    return None
