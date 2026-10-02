from flask import Flask, request, jsonify, render_template, render_template_string, redirect, send_file, Response
import webview
import warnings
import json
import threading
from threading import Thread
import os, sys
import datetime
import time
import pyaudio
import signal 
import re
import string
import random
import base64
from transcription_manager import TranscriptionManager
from subject_manager_2 import SubjectManager
from recording_manager import RecordingManager
from test_manager import TestManager
from emotibit_streamer_2 import EmotiBitStreamer
from vernier_manager import VernierManager
from ser_manager3 import SERManager
from audio_file_manager import AudioFileManager
from form_manager import FormManager
from timestamp_manager import TimestampManager
from werkzeug.utils import secure_filename

app = Flask(__name__)
emotibit_thread = None

PORT_NUMBER = 8000
EMOTIBIT_PORT_NUMBER = 9005

# Class instances stored in global scope 
# NOTE: These could be moved to Flask g instance to further reduce global access
subject_manager = SubjectManager() 
recording_manager = RecordingManager('tmp/recording.wav') 
test_manager = TestManager()
emotibit_streamer = EmotiBitStreamer(EMOTIBIT_PORT_NUMBER)
audio_file_manager = AudioFileManager('tmp/recording.wav', 'tmp') # tmp folder is a backup in case the root isn't set
ser_manager = SERManager()
form_manager = FormManager()
timestamp_manager = TimestampManager()
vernier_manager = VernierManager()
transcription_manager = TranscriptionManager()

update_message = None
update_event = threading.Event()

##################################################################
## Routes 
##################################################################
@app.route('/process_audio_files', methods=['POST'])
def process_audio_files() -> Response:
    """
    Processes audio files in the current subject's audio folder, transcribes them, 
    predicts the top 3 emotion and confidence scores, and writes the results to a CSV file.
    Returns:
        Response: A JSON response indicating the success of the operation with a message.
    """
    import csv
    global subject_manager, audio_file_manager, ser_manager
   
    data_rows = []

    # TODO: CHECK TO SEE IF THE METADATA IS NEEDED FOR THIS CSV
    subject_id = subject_manager.subject_id
    audio_folder = audio_file_manager.audio_folder
    experiment_name = subject_manager.experiment_name
    trial_name = subject_manager.trial_name

    date = datetime.datetime.now().strftime("%Y-%m-%d")

    emotion1 = None
    confidence1 = None
    emotion2 = None 
    confidence2 = None
    emotion3 =  None 
    confidence3 = None

    for file in os.listdir(audio_folder):
        if file.endswith(".wav"):
            parts = file.split("_")
            if parts[0] == subject_id and len(parts) > 2:
                transcription = transcribe_audio(os.path.join(audio_folder, file), timeout_seconds=240)
                emo_list = ser_manager.predict_emotion(os.path.join(audio_folder, file))
                timestamp = parts[1]

                emotion1, confidence1 = emo_list[0][0], emo_list[0][1]
                emotion2, confidence2 = emo_list[1][0], emo_list[1][1]
                emotion3, confidence3 = emo_list[2][0], emo_list[2][1]

                data_rows.append([timestamp, file, transcription, emotion1, confidence1, emotion2, confidence2, emotion3, confidence3])

    data_rows.sort(key=lambda x: x[0])
    csv_path = os.path.join(subject_manager.subject_folder, f"{date}_{experiment_name}_{trial_name}_{subject_id}_SER.csv")

    with open(csv_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Timestamp", "File_Name", "Transcription", "SER_Emotion_Label_1", "SER_Confidence_1", "SER_Emotion_Label_2", "SER_Confidence_2", "SER_Emotion_Label_3", "SER_Confidence_3" ])
        for row in data_rows:
            writer.writerow(row)   

    print(f"CSV file created: {csv_path}")
    return jsonify({'message': 'Audio files processed successfully.', 'path': csv_path}), 200

@app.route('/upload_survey', methods=['POST'])
def upload_survey() -> Response:
    """
    Route for adding surveys to the form manager.
    Args:
        survey_name (str): The name of the survey.
        url (str): The URL of the survey.
    Returns:
        Response: A JSON response indicating the status of the survey
    """
    global subject_manager, form_manager
    try:
        survey_name = request.form.get('survey_name')
        print(f"Survey name: {survey_name}")
        survey_name = form_manager.clean_string(survey_name)
        url = request.form.get('survey_url')
        print(f"Survey URL: {url}")
        message = form_manager.add_survey(survey_name, url)
        
        if message == "Survey already exists.":
            return jsonify({'message': f'{message}'}), 400
        elif message == "surveys.json is missing.":
            return jsonify({'message': f'{message}'}), 400
        
        return jsonify({'message': 'Survey added successfully.'}), 200
  
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 400

@app.route("/survey/<name>")
def survey(name):
    """Retrieve the survey URL by name and return an HTML page."""
    global form_manager
    name = form_manager.clean_string(name)
    url = form_manager.get_survey_url(name)

    if url == "not found":
        return jsonify({'message': 'No survey found with that name.'})
    
    print(f"Sending survey: {url}")
    return render_template("survey.html", survey_url=url)

@app.route("/get_subject_id", methods=['GET'])
def get_subject_id():
    global subject_manager

    subject_id = subject_manager.subject_id
    if not subject_id:
        subject_id = "No Subject ID available"

    return jsonify({'subject_id': f"{subject_id}"})

@app.route('/set_condition', methods=['POST'])
def set_condition() -> Response:
    global emotibit_streamer, vernier_manager
    data = request.get_json()
    condition = data.get('condition')
    try:
        emotibit_streamer.condition = condition
        vernier_manager.condition = condition

        print("Condition set to: ", emotibit_streamer.condition)

        return jsonify({'status': 'Condition set.'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    
@app.route('/set_event_marker', methods=['POST'])
def set_event_marker():
    global emotibit_streamer, vernier_manager
    data = request.get_json()
    event_marker = data.get('event_marker')
    try:
        emotibit_streamer.event_marker = event_marker
        vernier_manager.event_marker = event_marker

        # DEBUG
        print("Event marker set to: ", event_marker)

        return jsonify({'status': 'Event marker set.'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/complete_task', methods=['POST'])
def complete_task() -> Response:
    global update_message
    request_data = request.get_json(silent=True) or {}
    task_id = request_data.get('task_id', '')
    action = request_data.get('action', 'complete')

    if not task_id or action not in {'complete', 'reopen'}:
        return jsonify({'error': 'A task ID and valid action are required.'}), 400

    is_completed = action == 'complete'
    event_type = 'task_completed' if is_completed else 'task_reopened'
    action_label = 'completed' if is_completed else 'reopened'

    update_message = {
        'event_type': event_type,
        'task_id': task_id,
        'message': f'Task {task_id} {action_label}.'
    }
    
    update_event.set()
    return jsonify(success=True, task_id=task_id, status=action_label), 200

@app.route('/status_update', methods=['POST'])
def status_update() -> Response:
    global update_message
    status = request.json.get('status', '')

    update_message = {
        'event_type': 'status_update',
        'message': status
    }
    
    update_event.set()
    return jsonify(success=True), 200

@app.route('/send_error', methods=['POST'])
def send_error() -> Response:
    global update_message
    error_message = request.json.get('error', '')
    update_message = {
        'event_type': 'error',
        'message': error_message
    }
    
    update_event.set()
    return jsonify(success=True), 200

@app.route('/stream')
def stream():
    def event_stream():
        global update_message
        last_message = None

        while True:
            update_event.wait()
            if update_message != last_message:
                last_message = update_message
                yield f"data: {json.dumps(update_message)}\n\n"

            update_event.clear()

    return Response(event_stream(), content_type="text/event-stream")

@app.route('/reset_ser_question_index', methods=['POST'])
def reset_ser_question_index() -> Response:
    global test_manager

    test_manager.current_ser_question_index = 0

    return jsonify({'status': 'SER questions reset'})
    
@app.route('/get_ser_question', methods=['GET'])
def get_ser_question() -> Response:
    """
    Retrieve the current SER (Speech Emotion Recognition) question and increment the question index.
    This function fetches the current SER question from the test manager's list of questions,
    increments the question index, and returns the question in a JSON response. If the index
    exceeds the number of available questions, it stops the recording and resets the index.
    Returns:
        Response: A JSON response containing the current question or a completion message.
    Raises:
        Exception: If an error occurs during the process, a JSON response with the error message is returned.
    """
    global test_manager, recording_manager
    questions = test_manager.ser_questions.get('questions', [])
    
    try:
        if 0 <= test_manager.current_ser_question_index < len(questions):
            question = questions[test_manager.current_ser_question_index]['text']
            test_manager.current_ser_question_index += 1

            # DEBUG
            print(f"SER Question Index: {test_manager.current_ser_question_index}")
            print(f"SER Question: {question}")

            return jsonify({'message': 'Question found', 'question': question})
        
        elif test_manager.current_ser_question_index >= len(questions):
            recording_manager.stop_recording()
            # test_manager.current_ser_question_index = 0

            return jsonify({'message': 'SER task completed.'}), 200  

    except Exception as e:
        print(f"Error in get_ser_question: {e}") 
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/process_ser_answer', methods=['POST'])  
def process_ser_answer() -> Response:
    """
    Processes the user's spoken answer for a SER (Speech Emotion Recognition) question.
    This function performs the following steps:
    Set the event markers
    1. Stops the current audio recording.
    2. Renames the audio file based on the subject's ID and the current question index.
    3. Saves the renamed audio file to the 'audio_files' directory.
    4. Returns a JSON response indicating the status of the submission.
    Returns:
        - Response: A JSON response with the status of the answer submission.
            If successful, returns {'status': 'Answer submitted.'}.
            If an error occurs, returns {'status': 'error', 'message': str(e)} with a 400 status code.
    """
    global subject_manager, recording_manager, audio_file_manager, test_manager

    recording_manager.stop_recording()

    try:
        ts = recording_manager.timestamp
        end_time = recording_manager.end_timestamp
        print(f"Stop time from recording manager: {end_time}")
        id = subject_manager.subject_id

        file_name = f"{id}_{ts}_ser_baseline_question_{test_manager.current_ser_question_index}.wav"

        # DEBUG
        print(f"Audio File Name: {file_name}")

        subject_manager.append_data({'Timestamp': ts, 'Time_Stopped': end_time, 'Event_Marker': 'ser_baseline', 'Condition': 'None', 'Audio_File': file_name})
        audio_file_manager.save_audio_file(file_name)

        return jsonify({'status': 'Answer processed successfully.'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/get_first_question', methods=['POST'])
def get_first_question() -> Response:
    global test_manager, recording_manager
    test_manager.current_question_index = 0
    questions = test_manager.get_task_questions(test_manager.current_test_index)
    try:
        if questions is None:
            return jsonify({"message": "No questions found."})
        else:
            recording_manager.start_recording()
            question = questions[test_manager.current_question_index]
            
            return jsonify({'message': 'Question found.', 'question': question['question'], "test_index": test_manager.current_test_index})
    except Exception as e:
        return jsonify({'message': 'Error getting first question.', 'error': str(e)}), 400

@app.route('/confirm_transcription', methods=['POST'])
def confirm_transcription() -> Response:
    """
    Stops the current recording, transcribes the audio, and returns the transcription result.
    This function performs the following steps:
    1. Stops the current audio recording using the recording_manager.
    2. Transcribes the audio file.
    3. Updates the current answer in the test_manager with the transcribed text.
    4. Returns a JSON response with the transcription result, asking for confirmation.

    Returns:
        Response: A JSON response containing the transcription result and a confirmation prompt.
                  If an error occurs during transcription, returns a JSON response with an error message and a 400 status code.
    """
    global test_manager, recording_manager, audio_file_manager

    test_status = request.get_json().get('test_status')
    time_up = request.get_json().get('time_up')

    print("Stopping the recording...")
    recording_manager.stop_recording()

    try:
        if time_up:
            print("Recording stopped. Transcription set to 'time up'.")
            test_manager.current_answer = "Time up."
        else:
            print("Recording stopped. Transcribing....")
            
            test_manager.current_answer = transcribe_audio(audio_file_manager.recording_file)

            

        if test_status == "testEnded":
            return jsonify({'transcription': test_manager.current_answer, 'status': 'test has ended', 'message': 'Answer recorded and processed by endTest function.'})
        
        if time_up:
            return jsonify({'transcription': test_manager.current_answer, 'status': 'time is up.', 'message': 'Answer recorded.'})
        else:
            return jsonify({'transcription': f"I got: {test_manager.current_answer}. Is this correct (Y/N)?", 'status': 'Answer transcribed', 'message': 'Transcription complete'})

    except:
        return jsonify({'transcription': 'None', 'status': 'error', 'message': 'Something went wrong.'}), 400

@app.route('/process_answer', methods=['POST'])
def process_answer() -> Response:
    """
    Process the answer submitted by the user.
    This function handles the following tasks:
    - Retrieves the current test and its questions.
    - Extracts the test status from the request.
    - Generates a filename for the audio file based on the subject ID, timestamp, test, and question index.
    - Appends the transcription and other data to the subject's data file.
    - Handles errors related to transcription.
    - Updates the test and question indices based on the test status and correctness of the answer.
    - Returns a JSON response indicating the status of the operation.
    Returns:
        Response: A Flask JSON response indicating the status and result of the operation.
    """

    global recording_manager, subject_manager, audio_file_manager, test_manager
   
    current_test = test_manager.current_test_index

    if test_manager.current_test_index == 0:
        current_test_name = f"practice_stressor_test"
    else:
        current_test_name = f"stressor_test_{current_test}"

    questions = test_manager.get_task_questions(current_test)
    test_ended = request.get_json().get('test_status')
    id = subject_manager.subject_id

    try:
        if test_manager.current_question_index >= len(questions):
            test_manager.current_question_index = 0
            print(f"Question index is {test_manager.current_question_index}")
            return jsonify({'status': 'complete', 'message': 'Test complete. Please let the experimenter know that you have completed this section.', 'result': 'No more questions.'})

        if test_ended:
            recording_manager.stop_recording()
            print("Recording stopped. Transcribing....")
            time.sleep(0.1)
            transcription = transcribe_audio(audio_file_manager.recording_file)

            if test_manager.current_test_index != 0:
                ts = recording_manager.timestamp
                end_time = recording_manager.end_timestamp
                file_name = f"{id}_{ts}_{current_test_name}_question_{test_manager.current_question_index}.wav"

                print("Saving file...")
                audio_file_manager.save_audio_file(file_name)

                print("Saving data...")
                # Header structure: 'Timestamp', 'Event_Marker', 'Audio_File', 'Transcription', 'SER_Emotion', 'SER_Confidence'
                subject_manager.append_data({'Timestamp': ts, 'Time_Stopped': end_time, 'Event_Marker': current_test_name, 'Condition': 'None', 'Audio_File': file_name, 'Transcription': transcription})

                return jsonify({'status': 'times_up.', 'message': 'Test complete. Answer recorded and logged.', 'result': 'None'})
            else:
                return jsonify({'status': 'times_up.', 'message': 'Practice Test complete.', 'result': transcription})
             
        else:
            transcription = test_manager.current_answer

            if test_manager.current_test_index != 0:
                ts = recording_manager.timestamp
                end_time = recording_manager.end_timestamp
                file_name = f"{id}_{ts}_{current_test_name}_question_{test_manager.current_question_index}.wav"

                print("Saving file...")
                audio_file_manager.save_audio_file(file_name)

                print("Saving data...")
                # Header structure: 'Timestamp', Time_Stopped', 'Event_Marker', 'Condition', 'Audio_File', 'Transcription'
                subject_manager.append_data({'Timestamp': ts, 'Time_Stopped': end_time, 'Event_Marker': current_test_name, 'Condition': 'None', 'Audio_File': file_name,'Transcription': transcription})

            correct_answer = questions[test_manager.current_question_index]['answer']
            result = 'incorrect'

            if test_manager.check_answer(transcription, correct_answer):
                result = 'correct'
                test_manager.current_question_index += 1

                if test_manager.current_question_index >= len(questions):
                    test_manager.current_question_index = 0
                    print(f"Question index is {test_manager.current_question_index} and length of question file is {len(questions)}.")
                    return jsonify({'status': 'complete', 'message': 'Test complete. Please let the experimenter know that you have completed this section.', 'result': result})
                
            if result == 'incorrect':
                test_manager.current_question_index = 0
            
            print(f"Result: {result}")
            print("Starting the recording...")
            recording_manager.start_recording()

            return jsonify({'status': 'Answer successfuly processed', 'message': 'Recording started...', 'result': result})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/set_current_test', methods=['POST'])
def set_current_test() -> Response:
    global test_manager, transcription_manager
    test_number = request.get_json().get('test_number')
    if test_number is None:
        raise ValueError("Missing 'test_number' in request JSON")
    
    try: 
        test_manager.current_test_index = int(test_number)
        test_manager.current_question_index = 0
        
        # Clear stale results when Whisper is idle. A timed-out transcription
        # must not prevent the next MAT from loading.
        if int(test_number) > 0:
            transcription_manager.reset(lock_timeout=0.1)
        
        print(f"Test set to {test_number}.")
        print(f"Current Question Index: {test_manager.current_question_index}")
        return jsonify({'message': f'Test set to {test_number}.'}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/get_stream_active', methods=['GET'])
def get_stream_active() -> Response:
    global recording_manager
    stream_is_active = recording_manager.stream_is_active
    return jsonify({'stream_active': stream_is_active})

@app.route('/submit_experiment', methods=['POST'])
def submit_experiment() -> Response:
    global subject_manager

    experiment_name = request.form.get('experiment_name')
    trial_name = request.form.get('trial_name')

    if not experiment_name or not trial_name:
        return jsonify({"error": "Missing experiment_name or trial_name"}), 400
    
    subject_manager.experiment_name = form_manager.clean_string(experiment_name)
    subject_manager.trial_name = form_manager.clean_string(trial_name)
    subject_manager.categories = request.form.getlist('categories')

    # DEBUG
    print("Subject Experiment: ", subject_manager.experiment_name)
    print("Subject Trial: ", subject_manager.trial_name)
    print("Categories: ", subject_manager.categories)

    return jsonify({'message': 'Experiment and trial names submitted.'}), 200

@app.route('/upload_surveys_csv', methods=['POST'])
def upload_surveys_csv() -> Response:
    global subject_manager, form_manager
    if subject_manager.subject_folder is None:
        return jsonify({'message': 'Subject information is not set.'}), 400
   
    try:
        if 'csv_file' not in request.files:
            return jsonify({'message': 'No file part.'}), 400
        
        file = request.files['csv_file']

        if not file.filename or not file.filename.lower().endswith(".csv"):
            return jsonify({"message": "Invalid file type. Only CSV files are allowed."}), 400
        
        filename = secure_filename(file.filename)
        temp_file_path = os.path.join("tmp", filename)
        file.save(temp_file_path)  

        base_name = os.path.splitext(file.filename)[0]
        survey_name = base_name.split(" (")[0]
        survey_name = form_manager.clean_string(survey_name)
        survey_name = f"{subject_manager.subject_id}_{survey_name}_response.csv"

        file_path = os.path.join(subject_manager.subject_folder, survey_name)

        response_found = form_manager.find_survey_response(temp_file_path, file_path, subject_manager.subject_email)
        if not response_found:
            return jsonify({'message': 'Survey response or email column not found.'}), 400
        else:
            return jsonify({'message': 'Survey response found.', 'file_path': file_path}), 200
        
    except Exception as e:
        return jsonify({'error': 'Error uploading file.'}), 400

@app.route('/import_emotibit_csv', methods=['POST'])
def import_emotibit_csv() -> Response:
    """
    Handles the import of EmotiBit CSV files via POST request.
    This route allows uploading one or multiple EmotiBit CSV files associated with the current subject.
    Files are saved to the data folder specified in the global `emotibit_streamer` object, with filenames
    including the session start time and subject ID. If a file with the same name already exists, a counter
    is appended to avoid overwriting.
    Request:
        - Method: POST
        - Form Data:
            - 'emotibit_file': Single file upload (for backward compatibility)
            - 'emotibit_files': Multiple file upload (list of files)
    Returns:
        - 200 OK: On successful upload of one or more files. Returns JSON with file paths and upload details.
        - 400 Bad Request: If no files are provided, subject information is not set, or all uploads fail.
        - 200 OK: If some files succeed and some fail, returns details for both successes and errors.
    Response JSON Example (success):
        {
            "message": "File(s) uploaded successfully.",
            "file_path": "...",           # For single file
            "file_paths": [...],          # For multiple files
            "uploaded_files": [...],      # List of uploaded file details
            "errors": [...]               # List of error messages (if any)
        }
    Response JSON Example (failure):
        {
            "errors": [...]
        }
    """
    global emotibit_streamer
    
    if emotibit_streamer.data_folder is None:
        print("EmotiBit data folder not set.")
        return jsonify({'message': 'Subject information is not set.'}), 400
    
    files = []
    if 'emotibit_file' in request.files:
        # Single file upload (backwards compatibility)
        files = [request.files['emotibit_file']]
    elif 'emotibit_files' in request.files:
        files = request.files.getlist('emotibit_files')
    else:
        return jsonify({'message': 'No file part.'}), 400
    
    if not files:
        return jsonify({'message': 'No files selected.'}), 400
    
    uploaded_files = []
    errors = []
    
    for i, file in enumerate(files):
        print(f"Processing file {i+1}: {file.filename}")
        
        if not file.filename or not file.filename.lower().endswith(".csv"):
            errors.append(f"File '{file.filename}': Invalid file type. Only CSV files are allowed.")
            continue
        
        if i == 0:
            new_filename = f"{emotibit_streamer.time_started}_{subject_manager.subject_id}_emotibit_ground_truth.csv"
        else:
            new_filename = f"{emotibit_streamer.time_started}_{subject_manager.subject_id}_emotibit_ground_truth_{i+1}.csv"
        
        file_path = os.path.join(emotibit_streamer.data_folder, new_filename)
        
        counter = 1
        original_path = file_path
        while os.path.exists(file_path):
            base_name = new_filename.rsplit('.csv', 1)[0]
            if i == 0:
                file_path = os.path.join(emotibit_streamer.data_folder, f"{base_name}_{counter}.csv")
            else:
                if f"_{i+1}" in base_name:
                    base_name = base_name.replace(f"_{i+1}", "")
                file_path = os.path.join(emotibit_streamer.data_folder, f"{base_name}_{i+1}_{counter}.csv")
            counter += 1
        
        try:
            file.save(file_path)
            uploaded_files.append({
                'original_name': file.filename,
                'saved_name': os.path.basename(file_path),
                'file_path': file_path
            })
            print(f"File saved: {file_path}")
        except Exception as e:
            errors.append(f"File '{file.filename}': Error saving file - {str(e)}")
            print(f"Error saving file {file.filename}: {e}")

    if uploaded_files and not errors:
        if len(uploaded_files) == 1:
            return jsonify({
                "success": True, 
                "message": "File uploaded successfully.", 
                "file_path": uploaded_files[0]['file_path']
            }), 200
        else:
            file_paths = [f['file_path'] for f in uploaded_files]
            return jsonify({
                "success": True, 
                "message": f"{len(uploaded_files)} files uploaded successfully.", 
                "file_paths": file_paths,
                "uploaded_files": uploaded_files
            }), 200
    
    elif uploaded_files and errors:
        file_paths = [f['file_path'] for f in uploaded_files]
        return jsonify({
            "success": True, 
            "message": f"{len(uploaded_files)} files uploaded successfully, {len(errors)} failed.", 
            "file_paths": file_paths,
            "uploaded_files": uploaded_files,
            "errors": errors
        }), 200
    
    else:
        return jsonify({
            "success": False, 
            "message": "All file uploads failed.", 
            "errors": errors
        }), 400

@app.route('/submit', methods=['POST'])    
def submit() -> Response:
    """
    Handle the submission of user information and set up necessary resources for the experiment.
    This function performs the following steps:
    1. Validates that the experiment and trial names are set.
    2. Cleans and retrieves the subject's first name, last name, and email from the form data.
    3. Validates the email address format.
    4. Encrypts the subject's email to generate a unique subject ID.
    5. Cleans and retrieves the subject's PID and class name from the form data.
    6. Sets the subject information in the subject manager.
    7. Configures the audio file manager and emotibit streamer with the subject's folder.
    8. Initializes the HDF5 file for the EmotiBit streamer.
    9. Generates custom URLs for the PSS10, exit, and demographics surveys.
    Returns:
        Response: A JSON response indicating the success or failure of the operation.
        - On success: Returns a JSON object with a success message and URLs for the PSS10, exit, and demographics surveys, with a 200 status code.
        - On failure: Returns a JSON object with an error message, with a 400 status code.
    """
    global subject_manager, form_manager, audio_file_manager, emotibit_streamer, vernier_manager

    experiment_name = subject_manager.experiment_name
    trial_name = subject_manager.trial_name
    try:
        if experiment_name is None or trial_name is None:
            return jsonify({'message': 'Experiment and trial names must be set.'}), 400
        
        else:
            subject_first_name = form_manager.clean_string(request.form.get('first_name'))
            subject_last_name = form_manager.clean_string(request.form.get('last_name'))
            subject_email = request.form.get('email').lower().strip().replace(" ", "_")
            subject_assigned_id = request.form.get('assignedID')

            if not is_valid_email(subject_email):
                return jsonify({'message': 'Invalid email address.'}), 400
            
            subject_id = encrypt_id(subject_email)
            form_manager.add_to_subject_ids(subject_id, subject_first_name, subject_last_name, subject_email)

            subject_manager.subject_first_name = subject_first_name
            subject_manager.subject_last_name = subject_last_name
            subject_manager.subject_email = subject_email 
            subject_PID = form_manager.clean_string(request.form.get('PID')) 
            subject_class = form_manager.clean_string(request.form.get('class'))
            subject_manager.set_subject({"id": subject_id, "PID": subject_PID, "class_name": subject_class, "assigned_id": subject_assigned_id})

            audio_file_manager.set_audio_folder(subject_manager.subject_folder)
            emotibit_streamer.set_data_folder(subject_manager.subject_folder)
            emotibit_streamer.set_filenames(subject_id)

            vernier_manager.set_data_folder(subject_manager.subject_folder) 
            vernier_manager.set_filenames(subject_id)

            pss10 = form_manager.get_custom_url("pss10", subject_manager.subject_id)
            exit_survey = form_manager.get_custom_url("exit", subject_manager.subject_id)
            demographics = form_manager.get_custom_url("demographics", subject_manager.subject_id)
            ipr_survey = form_manager.get_custom_url("ipr", subject_manager.subject_id)

            return jsonify({'message': 'User information submitted.', 'pss10': pss10, 'demographics': demographics, 'exit_survey': exit_survey, 'ipr_survey': ipr_survey}), 200
        
    except Exception as e:
        return jsonify({'message': 'Error processing request.'}), 400

@app.route('/encrypt_subject', methods=['POST'])
def encrypt_subject() -> Response:
    global form_manager

    email = request.form.get('email').lower().strip().replace(" ", "_")

    if not is_valid_email(email):
        return jsonify({'error': 'Invalid email address.'}), 400
    
    subject_id = encrypt_id(email)

    return jsonify({'message': subject_id})

@app.route('/decrypt_subject', methods=['POST'])
def decrypt_subject() -> Response:
    try:
        email = decrypt_id(request.form.get('id_string'))

        firstname, lastname = form_manager.get_subject_name(email)
        if firstname is None:
            return jsonify({'message': 'Subject not found.'}), 400
        
        fullname = f"{firstname} {lastname}"

        return jsonify({'full_name': fullname, 'email': email, 'message': 'Subject found.'}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/shutdown', methods=['POST'])
def shutdown() -> Response:
    response = jsonify ({'message': 'Server shutting down...'})
    response.status_code = 200
    threading.Thread(target=shutdown_server).start() 

    return response

##################################################################
## Audio Routes
##################################################################
@app.route('/reset_audio', methods=['POST'])
def reset_audio() -> Response:
    """
    Reset the audio system by terminating the current PyAudio instance and creating a new one.
    This function is useful for reinitializing the audio system in case of issues or changes in configuration.
    Returns:
        Response: A JSON response indicating the success of the operation.
    """
    global recording_manager
    try:
        recording_manager.reset_audio_system()
        return jsonify({'message': 'Audio system reset successfully. Please test input and output before preceding.'}), 200
    except Exception as e:
        return jsonify({'message': f'Error resetting audio system: {str(e)}'}), 400
    
@app.route('/test_audio', methods=['POST'])
def test_audio() -> Response:
    """
    Endpoint to test audio recording and transcription.
    This function stops the current audio recording, transcribes the audio file,
    and returns the transcription result in a JSON response. It handles various
    exceptions that may occur during the transcription process and returns
    appropriate error messages.
    Returns:
        Response: A JSON response containing the transcription result or an error message.
            - If transcription is successful, returns {'result': transcription}.
            - If transcription could not understand the audio, returns {'result': 'error', 'message': "Sorry, I could not understand the response."} with status code 400.
            - If there is a request error with the Google Speech Recognition service, returns {'result': 'error', 'message': "Could not request results from Google Speech Recognition service."} with status code 400.
            - If an unknown value error occurs, returns {'status': 'error', 'message': "Sorry, I could not understand the response."} with status code 400.
            - If a request error occurs, returns {'status': 'error', 'message': f"Could not request results from Google Speech Recognition service; {e}"} with status code 500.
            - If any other exception occurs, returns {'status': 'error', 'message': str(e)} with status code 500.
    """
    global recording_manager
    try:
        recording_manager.stop_recording()
        transcription = transcribe_audio(recording_manager.recording_file)    
      
        return jsonify({'result': transcription})

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/get_audio_devices', methods=['GET'])
def get_audio_devices() -> Response:
    global recording_manager
    audio_devices = recording_manager.get_audio_devices()
    return jsonify(audio_devices)

@app.route('/set_device', methods=['POST'])
def set_device() -> Response:
    global recording_manager
    data = request.get_json()
    try:
        device_index = int(data.get('device_index'))
    except (TypeError, ValueError):
        return jsonify({'message': 'Invalid device index'}), 400

    try:
        recording_manager.set_device(device_index)
        return jsonify({'message': 'Device index set.'})
    except Exception as e:
        return jsonify({'message': f'Error setting device index: {str(e)}'}), 400


@app.route('/record_task_audio', methods=['POST'])
def record_task_audio():
    """
    Handle audio recording tasks based on the provided action.
    This function processes JSON data from a request to either start or stop an audio recording.
    It manages the recording state, updates event markers, and saves audio files with appropriate metadata.
    Request JSON structure:
    {"action": "start" or "stop", "question": <question_number>,"event_marker": <event_marker_text>}
    Returns:
        Response: A JSON response with a message indicating the result of the action and an HTTP status code.
        - If action is 'start': {"message": "Recording started."}, 200
        - If action is 'stop':  {"message": "Recording stopped."}, 200
        - If action is invalid: {"message": "Invalid action."}, 400
    """
    global recording_manager, timestamp_manager, subject_manager, vernier_manager
    data = request.get_json()
    action = data.get('action')
    question = data.get('question')
    event_marker = data.get('event_marker')
    condition = data.get('condition')
    event_marker = f"{event_marker}_{question}"
    
    try:
        if action == 'start':
            recording_manager.start_recording()
            emotibit_streamer.event_marker = event_marker
            vernier_manager.event_marker = event_marker

            start_time = 10 # seconds
            while not recording_manager.stream_is_active:
                if time.time() - start_time > 10:
                    return jsonify({'message': 'Error starting recording.'}), 400
                time.sleep(0.5)

            return jsonify({'message': 'Recording started...'}), 200
        
        elif action == 'stop':
            recording_manager.stop_recording()
            ts = recording_manager.timestamp
            end_time = recording_manager.end_timestamp
            id = subject_manager.subject_id

            file_name = f"{id}_{ts}_{event_marker}.wav"

            # Header structure: 'Timestamp', 'Event_Marker', 'Transcription', 'SER_Emotion', 'SER_Confidence'
            subject_manager.append_data({'Timestamp': ts, 'Time_Stopped': end_time, 'Event_Marker': event_marker, 'Condition': condition, 'Audio_File': file_name})
            audio_file_manager.save_audio_file(file_name)

            return jsonify({'message': 'Recording stopped.'}), 200
        else:
            return jsonify({'message': 'Invalid action.'}), 400
        
    except Exception as e:
        return jsonify({'error': 'Error processing request.'}), 400
      
@app.route('/record_task', methods=['POST'])
def record_task() -> Response:
    """
    Endpoint to handle general task audio recording.
    This function processes incoming JSON requests to start or stop audio recording.
    The function performs the following actions:
        - If the action is 'start', it returns a success message. The "start_recording" route is called from the client.
        - If the action is 'stop', it stops the recording, splits the audio into segments, generates
            timestamps, transcribes the audio, predicts emotions, and stores the results in the subject data.
    NOTE: This function will split audio into segments set by "segment_duration". The Time_Stopped field
        in the subject data will therefore be the starting timestamp + the segment duration. It WILL NOT necessarily correspond
        to times in which the subject was speaking.
    Returns:
        - Response: A JSON response indicating the result of the action with an appropriate HTTP status code.
    Raises:
        - Exception: If any error occurs during the processing of the request, an error message is returned
                   with a 400 HTTP status code.
    """
    global recording_manager, subject_manager, audio_file_manager
    global timestamp_manager, emotibit_streamer, vernier_manager

    try:
        data = request.get_json()
        event_marker = data.get('event_marker')
        condition = data.get('condition')
        action = data.get('action')
        
        if action == 'start':
            recording_manager.start_recording()
            emotibit_streamer.event_marker = event_marker
            emotibit_streamer.condition = condition
            vernier_manager.event_marker = event_marker
            vernier_manager.condition = condition

             # DEBUG
            print(f"EmbotiBit Event Marker: {emotibit_streamer.event_marker}")
            print(f"EmbotiBit Condition: {emotibit_streamer.condition}")
            print(f"Vernier Event Marker: {vernier_manager.event_marker}")
            print(f"Vernier Condition: {vernier_manager.condition}")

            return jsonify({'message': 'Recording started.'}), 200
        
        elif action == 'stop':
            recording_manager.stop_recording()
            emotibit_streamer.event_marker = 'subject_idle'
            emotibit_streamer.condition = 'None'
            vernier_manager.event_marker = 'subject_idle'
            vernier_manager.condition = 'None'
            
            # DEBUG
            print(f"EmbotiBit Event Marker: {emotibit_streamer.event_marker}")
            print(f"EmbotiBit Condition: {emotibit_streamer.condition}")

            id = subject_manager.subject_id
            audio_segments = audio_file_manager.split_wav_to_segments(id, event_marker, audio_file_manager.recording_file, 60, "tmp/")

            audio_segments = sorted(audio_segments, key=lambda x: 
                                    int(os.path.splitext(os.path.basename(x))[0].split('_')[-1]))
            
            for segment in audio_segments:
                key = os.path.splitext(os.path.basename(segment))[0].split('_')[-1]
                print(f"Segment: {segment}, Key: {key}")

            segment_duration = 20
            start_time = recording_manager.timestamp
            
            timestamps = generate_timestamps(start_time, segment_duration, "tmp/")

            task_data = []
            for ts, fn in zip(timestamps, audio_segments):
                ts_dt = datetime.datetime.fromisoformat(ts)
                time_stopped_dt = ts_dt + datetime.timedelta(seconds=segment_duration)
                task_data.append({
                    'Timestamp': ts,
                    'Time_Stopped': time_stopped_dt.isoformat(timespec='seconds'),
                    'Event_Marker': event_marker,
                    'Condition': condition,
                    'Audio_File': fn
                })
            
            for data in task_data:
                subject_manager.append_data(data)
            
            audio_file_manager.backup_tmp_audio_files()

            return jsonify({'message': 'Audio successfully processed.', 'event_marker': event_marker}), 200
        else:
            print("Invalid Action")
            return jsonify({'message': 'Invalid action.'}), 400
        
    except Exception as e:
        print(f"Exception: {str(e)}")
        return jsonify({'message': 'Error processing request.'}), 400

@app.route('/start_recording', methods=['POST'])    
def start_recording() -> Response:
    global recording_manager
    try:
        recording_manager.start_recording()
        start_time = time.time()

        timeout = 10 # seconds
        while not recording_manager.stream_is_active:
            if time.time() - start_time > timeout:
                return jsonify({'status': 'Error starting recording.'}), 400
            time.sleep(0.5)

        return jsonify({'status': 'Recording started.'}), 200
    except Exception as e:
        return jsonify({'status': 'Error starting recording.'}), 400

##################################################################
## Views 
##################################################################
@app.route('/prs')
def prs():
    """
    Generates and returns an HTML template for the PRS (Perceived Restorativeness Scale) task.
    The HTML template includes:
    - Instructions for the PRS task.
    - An introductory audio file.
    - A list of PRS audio files that are randomly shuffled.
    - A wait message audio file that plays last.
    - Recording buttons for subject responses.
    Returns:
        str: Rendered HTML template with the introductory audio file and shuffled PRS audio files.
    """
    AUDIO_DIR = 'static/prs_audio'
    intro = "1-PRS-Intro.mp3"
    wait_message = "Wait_For_Instructions.mp3"
    
    # Exclude both intro and wait_message from the randomized PRS audio files
    prs_audio_files = [f for f in os.listdir(AUDIO_DIR) if f.endswith('.mp3') and f != intro and f != wait_message]
    random.shuffle(prs_audio_files)
    
    html_template = r"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PRS</title>
        <script src="{{ url_for('static', filename='js/scripts.js') }}"></script>
        <link rel="stylesheet" href="{{ url_for('static', filename='css/styles.css') }}">
    </head>
    <body>
        <h1>PRS Task</h1>
        <h2>Instruction Text</h2>
        <ul>
            <li>For the next section of the experiment, we will be asking you to rate the extent to which a given statement describes your experience in this room.</li> 
            <li>The scale will be from 0 to 6. An answer of 0 means "Not at all" and an answer of 6 means "Completely".</li> 
            <li>After each question, you can take as much time as you need to think about it before speaking your response aloud. Then, you will provide a reason for each rating you provide.</li> 
            <li>The statements will begin now. As a reminder, you will answer with a number from 0 to 6, with 0 being "Not at all" and 6 being "Completely".</li>
            <li>Please provide a brief explanation for your answer after each question.</li>
        </ul><br>
        <div id="intro">
            <h3>Introduction</h3>
            <audio id="intro-audio-player" controls>
                <source src="{{ url_for('static', filename='prs_audio/' + intro) }}" type="audio/mpeg">
                Your browser does not support the audio element.
            </audio><br>
        </div><br>
        
        <!-- Wait message audio (hidden, will be played programmatically) -->
        <audio id="wait-message-audio" style="display: none;">
            <source src="{{ url_for('static', filename='prs_audio/' + wait_message) }}" type="audio/mpeg">
            Your browser does not support the audio element.
        </audio>
        
        <div id="container">
            {% for audio in audio_files %}
            <div class="audio-container">
                <audio controls data-audio-index="{{ loop.index }}">
                    <source src="{{ url_for('static', filename='prs_audio/' + audio) }}" type="audio/mpeg">
                    Your browser does not support the audio element.
                </audio>
                <div class="recording-status" id="audio{{ loop.index }}-recording-status"></div>
            </div>
            {% endfor %}
        </div>
        <script>
            document.addEventListener("DOMContentLoaded", function () {
                const introAudio = document.getElementById("intro-audio-player");
                const waitMessageAudio = document.getElementById("wait-message-audio");
                const acontainer = document.getElementById("container");
                let audioElements = Array.from(document.querySelectorAll("audio[data-audio-index]"));
                let currentIndex = 0;

                function shuffleArray(array) {
                    for (let i = array.length - 1; i > 0; i--) {
                        const j = Math.floor(Math.random() * (i + 1));
                        [array[i], array[j]] = [array[j], array[i]];
                    }
                }
                shuffleArray(audioElements);
                audioElements.forEach(container => {
                    container.style.display = "block";
                    acontainer.append(container);
                });
                
                const eventMarker = localStorage.getItem('currentEventMarker');
                const condition = localStorage.getItem('currentCondition');

                setEventMarker(eventMarker);
                setCondition(condition);

                function startRecordingForSegment(audioElement, baseName) {
                    const statusElement = audioElement.parentElement.querySelector(".recording-status");
                    statusElement.innerText = `Recording started for ${baseName}...`;
                    try {
                        emarker = eventMarker + "_" + baseName;
                        setEventMarker(emarker);
                        startRecording();
                        playBeep(); // Play initial beep
                    
                        console.log(`Recording started for ${baseName}`);

                        setTimeout(() => {
                            playBeep();
                            setTimeout(playBeep, 500); 
                        }, 15000);

                        setTimeout(() => {
                            stopRecordingForSegment(audioElement, baseName);
                        }, 20000);
                    } catch (error) {
                        console.error("Recording failed:", error);
                    }
                }

                function stopRecordingForSegment(audioElement, baseName) {
                    const statusElement = audioElement.parentElement.querySelector(".recording-status");
                    console.log(`Stopping recording for ${baseName}`);
                    recordTaskAudio(eventMarker, condition, 'stop', baseName, statusElement);
                    statusElement.innerText = "Recording stopped.";
                    playNextAudio();
                }

                function playWaitMessage() {
                    console.log("Playing wait message...");
                    waitMessageAudio.play();
                    
                    waitMessageAudio.onended = function () {
                        console.log("Wait message finished.");
                        completeTask();
                    };
                }

                function completeTask() {
                    if (eventMarker === 'prs_1') {
                        setEventMarker('sart_3');
                    } else if (eventMarker === 'prs_2') {
                        setEventMarker('sart_6');
                    }
                    setCondition('None');
                    console.log("All audio segments completed.");
                }

                function playNextAudio() {
                    if (currentIndex < audioElements.length) {
                        let audio = audioElements[currentIndex];
                        let audioSrc = audio.querySelector("source").getAttribute("src");
                        let baseName = audioSrc.split('/').pop().replace(/\.[^/.]+$/, "");

                        audio.play();
                        console.log(`Playing audio: ${baseName}`);

                        audio.onended = function () {
                            console.log(`Finished audio: ${baseName}`);
                            startRecordingForSegment(audio, baseName);
                        };

                        currentIndex++;
                    } else {
                        // All randomized PRS audio files completed, now play wait message
                        playWaitMessage();
                    }
                }

                introAudio.onended = function () {
                    console.log("Intro finished, starting first randomized audio...");
                    playNextAudio();
                };
            });
        </script>
    </body>
    </html>

    """
    return render_template_string(html_template, intro=intro, audio_files=prs_audio_files, wait_message=wait_message)

@app.route('/room_observation')
def room_observation() -> Response:
    return render_template('room_observation.html')

@app.route('/')
def home() -> Response:
    return render_template('index.html')

@app.route('/break_page', methods=['GET'])
def break_page() -> Response:
    return render_template('break_page.html')

@app.route('/subject_gui', methods=['GET'])
def subject_gui() -> Response:
    return render_template('subject_gui.html')

@app.route('/video/<filename>')
def video(filename) -> Response:
    video_path = os.path.join('static', 'videos', filename)
    return send_file(video_path)

@app.route('/test_page', methods=['GET'])
def test_page() -> Response:
    global test_manager
    # DEBUG
    print(f"Current quesiton index: {test_manager.current_question_index}")
    print(f"Current test index: {test_manager.current_test_index}")
    return render_template('test_page.html')

# Vernier ########################################################
@app.route('/start_vernier', methods=['POST'])
def start_vernier() -> None:
    global vernier_manager, subject_manager
    try:
        if subject_manager.subject_id is None:
            return jsonify({'message': 'Subject information is not set.'}), 400
        
        if vernier_manager.running:
            return jsonify({'message': 'Vernier belt is already running'}), 200
        
        vernier_manager.initialize_hdf5_file()

        time.sleep(1)

        start_result = vernier_manager.start()

        if "Error" in start_result:
            return jsonify({'message': 'Error starting Vernier stream.'}), 400
        
        print("Vernier belt has started.")

        time.sleep(1)

        vernier_manager.run()
        print("Vernier belt is running.")

        return jsonify({'message': 'Vernier stream started.'}), 200

    except Exception as e:
        print(f"An error occurred while trying to start Vernier stream: {str(e)}")
        return jsonify({'error': 'Error starting Vernier stream.'}), 400

@app.route('/stop_vernier', methods=['POST'])
def stop_vernier() -> None:
    global vernier_manager
    try:
        print("Stopping Vernier stream from app...")
        stop_result = vernier_manager.stop()
        print(stop_result)
        return jsonify({'message': stop_result}), 200
        
    except Exception as e:
        print(f"An error occurred while trying to stop Vernier stream: {str(e)}")
        return jsonify({'error': 'Error stopping Vernier stream.'}), 400
    
# Emotibit #######################################################
@app.route('/start_emotibit', methods=['POST'])
def start_emotibit() -> None:
    global emotibit_streamer
    try:
        if subject_manager.subject_id is None:
            print("EmotiBit subject ID not set.")
            return jsonify({'message': 'Subject information is not set.'}), 400
        
        print("Initializing EmobiBit data H5 file...")
        emotibit_streamer.initialize_hdf5_file()

        time.sleep(1)
        print("Starting EmotiBit stream...")
        emotibit_streamer.start()
        print("OSC server is streaming data.")
        return jsonify({'message': 'EmotiBit stream started.'}), 200

    except Exception as e:
        print(f"An error occurred while trying to start OSC stream: {str(e)}")

@app.route('/stop_emotibit', methods=['POST'])
def stop_emotibit() -> None:
    global emotibit_streamer
    try:
        if emotibit_streamer.is_streaming:
            emotibit_streamer.stop()
            print("OSC server stopped.")
            return jsonify({'message': 'EmotiBit stream stopped.'}), 200
        else:
            return jsonify({'message': 'EmotiBit stream is not active.'}), 400
        
    except Exception as e:
        print(f"An error occurred while trying to stop OSC stream: {str(e)}")
        return jsonify({'error': 'Error stopping EmotiBit stream.'}), 400

@app.route('/submit_pwd', methods=['POST'])
def submit_pwd() -> Response:
    password = "ucsdxrlab"
    guess = request.form.get('password')

    if guess == password:
        return jsonify({'message': 'Correct password.'}), 200
    else:
        return jsonify({'message': 'Incorrect password.'}), 400

# File and System Ops ############################################
def is_valid_email(email):
    """
    Validate if the provided email address is in a correct format.
    Args:
        email (str): The email address to validate.
    Returns:
        bool: True if the email address is valid, False otherwise.
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(pattern, email):
        return True
    else:
        return False
      
def encrypt_id(email: str) -> str:
    """Encrypts the subject's name and email into a reversible string."""
    email = email.lower().replace(" ", "_")
    bytes = email.encode('utf-8')
    obfuscated = base64.urlsafe_b64encode(bytes).decode('utf-8')
    print(f"Obfuscated: {obfuscated}")
    
    return obfuscated

def decrypt_id(obfuscated: str) -> tuple:
    """Decrypts the obfuscated string back into the original name and email."""
    decoded_bytes = base64.urlsafe_b64decode(obfuscated)
    email = decoded_bytes.decode('utf-8')
    
    return email

def preprocess_text(text) -> str:
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip()

def check_answer(transcription, correct_answers) -> bool:
    print(f"Transcription: {transcription}")
    transcription = preprocess_text(transcription)

    return any(word in correct_answers for word in transcription.split())

def shutdown_server() -> None:
    global emotibit_streamer, recording_manager, vernier_manager

    if recording_manager.audio is not None:
        recording_manager.audio.terminate()
        
    if emotibit_streamer.server_thread is not None:
        emotibit_streamer.stop()

    if vernier_manager.device_started and vernier_manager.running:
        vernier_manager.stop()

    time.sleep(1)
    pid = os.getpid()
    os.kill(pid, signal.SIGINT)

def generate_timestamps(start_time_dt, segment_duration=20, output_folder="tmp/") -> list:
    """
    Generate ISO 8601-formatted start timestamps for each audio segment file in the output folder.

    Args:
        start_time_dt (datetime.datetime or str): The starting time of the recording, as a datetime object or ISO string.
        segment_duration (int): Duration of each audio segment in seconds.
        output_folder (str): Directory containing the audio segment files.

    Returns:
        list: List of ISO 8601-formatted start timestamps (as strings), one for each segment file found.
    """
    import datetime
    import os

    print("Generating timestamps...")

    # If start_time_dt is a string, convert it to datetime
    if isinstance(start_time_dt, str):
        start_time_dt = datetime.datetime.fromisoformat(start_time_dt)

    # List all .wav files except 'recording.wav', sorted by segment index at the end of the filename
    segment_files = sorted(
        [f for f in os.listdir(output_folder) if f.endswith('.wav') and f != 'recording.wav'],
        key=lambda x: int(x.split('_')[-1].split('.')[0]) if x.split('_')[-1].split('.')[0].isdigit() else float('inf')
    )
    print("Segment files:", segment_files)

    # Generate ISO timestamps for each segment start time
    segment_timestamps = []
    for i in range(len(segment_files)):
        timestamp = start_time_dt + datetime.timedelta(seconds=i * segment_duration)
        segment_timestamps.append(timestamp.isoformat(timespec='seconds'))

    print(f"Generated timestamps: {segment_timestamps}")
    return segment_timestamps

##################################################################
## Speech Recognition 
##################################################################
def transcribe_audio(file, timeout_seconds=15) -> str:
    global transcription_manager

    result = transcription_manager.transcribe(file, timeout_seconds=timeout_seconds)
    return result if result is not None else "Sorry, I could not understand the response."

def run_flask():
    app.run(debug=False, use_reloader=False)

####################################################################
# Main Loop
####################################################################
if __name__ == '__main__':
    # Suppress warnings 
    warnings.filterwarnings("ignore")

    # TODO: For now, debug must be set to false when Emotibit streaming code is active.
    # This is because the port used by the EmotiBit will report as in use when in debug mode.
    # print(app.url_map)

    if not os.path.exists('tmp'):
        os.makedirs('tmp')

    app.run(port=PORT_NUMBER,debug=False, threaded=True)
