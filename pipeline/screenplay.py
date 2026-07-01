#!/usr/bin/env python3
'''Screenplay generation via Google Gemini Pro.'''
import json, logging, re
logger = logging.getLogger('pipeline.screenplay')

def generate_screenplay(idea, genre, audience, duration, style, language, gemini_key):
    '''Generate screenplay using Gemini 2.0 Flash.'''
    if not gemini_key:
        logger.warning('No Gemini key - returning fallback screenplay')
        return _fallback_screenplay(idea, genre, style), []

    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-2.0-flash')

        system_prompt = '''You are an expert cinematic screenwriter. Generate a complete screenplay as valid JSON only.
Return this exact structure:
{
  " title\: \Movie Title\,
 \scenes\: [
 {
 \sceneNum\: 1,
 \title\: \Scene Title\,
 \scriptText\: \Scene action description\,
 \characters\: [\Character Name\],
 \background\: \Detailed environment description for Veo 3\,
 \lighting\: \Lighting description\,
 \cameraAngle\: \Camera angle and movement\,
 \duration\: 15,
 \voiceText\: \Narrator or character dialogue\,
 \videoPrompt\: \Detailed Veo 3 text-to-video prompt photorealistic cinematic\,
 \cameraSimulation\: \Camera movement preset\
 }
 ],
 \characters\: [
 {
 \id\: \char-1\,
 \name\: \Character Name\,
 \description\: \Role in story\,
 \faceImg\: \Detailed visual description for consistency\,
 \clothing\: \Outfit description\,
 \personality\: \Personality traits\
 }
 ]
}'''

 user_prompt = f'''Create a {genre} screenplay for a {duration} video.
Target audience: {audience}
Style: {style}
Language: {language}
Movie idea: {idea}

Generate exactly 3 high-quality cinematic scenes. Each videoPrompt must be detailed enough for Google Veo 3 to generate photorealistic video.
Return ONLY valid JSON. No markdown. No explanation.'''

 response = model.generate_content(
 [system_prompt, user_prompt],
 generation_config=genai.GenerationConfig(
 temperature=0.8, max_output_tokens=4096,
 response_mime_type='application/json'
 )
 )

 text = response.text.strip()
 data = json.loads(text)
 scenes = data.get('scenes', [])
 characters = data.get('characters', [])
 logger.info(f'Gemini generated {len(scenes)} scenes, {len(characters)} characters')
 return scenes, characters

 except Exception as e:
 logger.error(f'Gemini screenplay failed: {e}')
 return _fallback_screenplay(idea, genre, style), []

def _fallback_screenplay(idea, genre, style):
 return [
 {'sceneNum': 1, 'title': 'Opening', 'scriptText': idea, 'characters': [], 'background': 'Cinematic establishing shot', 'lighting': 'Golden hour', 'cameraAngle': 'Wide establishing shot', 'duration': 20, 'voiceText': idea, 'videoPrompt': f'{idea}, {genre} style, {style}, cinematic, photorealistic, 4K', 'cameraSimulation': 'Slow Pan Left'},
 {'sceneNum': 2, 'title': 'Development', 'scriptText': 'Story develops...', 'characters': [], 'background': 'Medium environment', 'lighting': 'Dramatic shadows', 'cameraAngle': 'Medium close-up', 'duration': 20, 'voiceText': 'The story unfolds...', 'videoPrompt': f'Continuation of {idea}, dramatic, {style}, cinematic', 'cameraSimulation': 'Dramatic Zoom In'},
 {'sceneNum': 3, 'title': 'Resolution', 'scriptText': 'Story concludes...', 'characters': [], 'background': 'Resolution environment', 'lighting': 'Hopeful warm light', 'cameraAngle': 'Wide shot pulling back', 'duration': 20, 'voiceText': 'And so the story ends...', 'videoPrompt': f'Resolution of {idea}, hopeful, {style}, cinematic', 'cameraSimulation': 'Slow Pull Out'}
 ]
