from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from room_audio import get_room_audio_steps


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_room_audio_steps_filter_and_order_files(tmp_path):
    filenames = [
        '1-Task1-Intro.mp3',
        '2-Task1-PostObservation.mp3',
        '3-Task1-Q1.mp3',
        '4-Task1-Q2.wav',
        'Wait_For_Instructions.ogg',
        '.DS_Store',
        'transcript.txt',
    ]
    for filename in filenames:
        (tmp_path / filename).write_bytes(b'test')
    (tmp_path / 'not-an-audio-file.mp3').mkdir()

    steps = get_room_audio_steps(tmp_path, shuffle=lambda files: files.reverse())

    assert [(step['role'], step['filename']) for step in steps] == [
        ('intro', '1-Task1-Intro.mp3'),
        ('instructions', '2-Task1-PostObservation.mp3'),
        ('question', '4-Task1-Q2.wav'),
        ('question', '3-Task1-Q1.mp3'),
        ('wait', 'Wait_For_Instructions.ogg'),
    ]
    assert [step['question_number'] for step in steps] == [None, None, 1, 2, None]


def test_room_template_renders_every_discovered_audio_file(tmp_path):
    for filename in ('Intro.m4a', 'Question-B.flac', 'Question-A.aac', 'Wait_For_Instructions.mp3'):
        (tmp_path / filename).write_bytes(b'test')
    steps = get_room_audio_steps(tmp_path, shuffle=lambda files: None)
    environment = Environment(loader=FileSystemLoader(REPOSITORY_ROOT / 'templates'))
    environment.globals['url_for'] = lambda endpoint, filename: f'/static/{filename}'

    rendered = environment.get_template('room_observation.html').render(audio_steps=steps)

    for filename in (step['filename'] for step in steps):
        assert rendered.count(f'room_observation_audio/{filename}') == 1


def test_participant_labels_match_experimenter_workflow():
    participant_template = (REPOSITORY_ROOT / 'templates' / 'subject_gui.html').read_text()
    experimenter_template = (REPOSITORY_ROOT / 'templates' / 'index.html').read_text()
    expected_labels = [
        'Step 1 — Participant Information and Surveys',
        'Step 4a — Audio Setup',
        'Step 4b — Test Transcription',
        'Step 5 — Mood Q&amp;A (SER Baseline)',
        'Step 6 — SART Task 1',
        'Step 7 — Practice MAT',
        'Step 8 — MAT 1',
        'Step 9 — SART Task 2',
        'Step 10 — ZIPERS 1',
        'Step 12 — SART Task 3',
        'Step 13 — ZIPERS 2',
        'Step 14 — Break 1',
        'Step 15 — SART Task 4',
        'Step 16 — MAT 2',
        'Step 17 — SART Task 5',
        'Step 18 — ZIPERS 3',
        'Step 20 — SART Task 6',
        'Step 21 — ZIPERS 4',
        'Step 22 — Break 2',
        'Step 23 — Exit Survey',
    ]

    for label in expected_labels:
        assert label in participant_template
        assert label in experimenter_template
