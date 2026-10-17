import os
import random
import re


AUDIO_EXTENSIONS = {'.aac', '.flac', '.m4a', '.mp3', '.ogg', '.wav'}
ROOM_AUDIO_TRANSCRIPTS = {
    '1-Task1-Intro.mp3': 'Welcome. Please spend 60 seconds observing the space around you. Pay attention to all the details you notice: the lighting, furniture, objects, and any other features of the room. Afterward, you will be asked a series of questions about the space. Now begin observing the room.',
    '2-Task1-PostObservation.mp3': 'Now, you will answer a series of questions about the room. Feel free to look around the room as you answer. Speak your answers clearly. Please provide as much detail as possible within the given time for each question. Do your best to speak for the whole time. If you need time to think before you answer, please say your thought process aloud so that you are talking for the whole time. You will hear one beep after each prompt, indicating that you can begin talking. You will hear two beeps when you have 15 seconds remaining to finish your answer.',
    '3-Task1-Q1.mp3': 'Imagine describing this room to someone who cannot see it. Speak for two minutes and include as much detail as you can. Be detailed enough that someone could picture the space based on your description alone. You may begin now.',
    '4-Task1-Q2.mp3': "Now, we would like to know how you would rearrange the space to best accommodate or support different types of activities, such as chatting over a cup of coffee with someone or doing independent work. How would you move the furniture? You won't actually move it; just describe each activity and the corresponding arrangement. You can also suggest multiple different arrangements for the same activity. Your rearrangement might make the space more functional relative to certain activities, or more aesthetic, efficient, or any other change you find important. Think of as many different arrangements as possible that could help facilitate different activities. You will have three minutes. You may begin now.",
    'Wait_For_Instructions.mp3': 'Please wait for further instructions.',
}


def _natural_sort_key(filename):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', filename)]


def _audio_role(filename):
    normalized_name = re.sub(r'[^a-z0-9]+', '_', os.path.splitext(filename)[0].lower()).strip('_')
    if 'wait_for_instructions' in normalized_name or normalized_name.startswith('wait_'):
        return 'wait'
    if 'postobservation' in normalized_name or 'post_observation' in normalized_name or 'response_instructions' in normalized_name:
        return 'instructions'
    if 'intro' in normalized_name:
        return 'intro'
    return 'question'


def get_room_audio_steps(audio_dir, shuffle=random.shuffle):
    """Return playable Room Observation audio with fixed bookends and shuffled questions."""
    grouped_files = {'intro': [], 'instructions': [], 'question': [], 'wait': []}
    for filename in os.listdir(audio_dir):
        path = os.path.join(audio_dir, filename)
        extension = os.path.splitext(filename)[1].lower()
        if filename.startswith('.') or not os.path.isfile(path) or extension not in AUDIO_EXTENSIONS:
            continue
        grouped_files[_audio_role(filename)].append(filename)

    for filenames in grouped_files.values():
        filenames.sort(key=_natural_sort_key)
    shuffle(grouped_files['question'])

    steps = []
    question_number = 0
    for role in ('intro', 'instructions', 'question', 'wait'):
        for filename in grouped_files[role]:
            if role == 'question':
                question_number += 1
            steps.append({
                'filename': filename,
                'role': role,
                'question_number': question_number if role == 'question' else None,
                'transcript': ROOM_AUDIO_TRANSCRIPTS.get(filename),
            })
    return steps
