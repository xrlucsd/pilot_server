# Pilot Experiment Server

## A command center for running all applications during experiment

This is the active XR Lab-maintained repository.

**Installation**

**NOTE:** The best way to install ffmpeg and Portaudio on Mac is with HomeBrew. 

To install Homebrew, run the following command in Terminal:

    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
Install portaudio with:

    brew install portaudio
Install ffmpeg with:

    brew install ffmpeg
Install postgreSQL with:

    brew install postgresql@15 
Install whisper with:

    pip install git+https://github.com/openai/whisper.git
Install all other packages with:

    pip install -r requirements.txt
Retrieve the SER model here: https://drive.google.com/drive/folders/1w3-QJEl_pzuIkiOuDUejkFp9x8Mfs4LF?usp=drive_link

Place the SER_MODEL folder at the root of the server: /EXP_SERVER/.

Retrieve the video files here: https://drive.google.com/drive/folders/1nBtfuXfNhhzsi4oFjVRUnYrbLneVJI7c?usp=drive_link

Place the videos folder inside the static folder of the server: /EXP_SERVER/static/.

**Instructions for server**

To run the server, simply open a terminal, navigate to the root folder and type:
python exp_server.py

You should see the following result in Terminal: 
 
    * Serving Flask app 'exp_serve'
    * Debug mode: on
    WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
    * Running on http://127.0.0.1:5000
    Press CTRL+C to quit
    * Restarting with watchdog (fsevents)
    * Debugger is active!
    * Debugger PIN: 122-354-517

* On Mac, CMD+click on the listed http address and the server will launch a webpage in your default browser
* To shutdown the server in the browser, click "Shutdown Server"
* To shutdown in terminal, run "ctrl+c"

**NOTE:** DO NOT remove the any of the html pages from the templates folder. This is where Flask will always look for them. Your home http address may vary.
### Classes

**Please note that at the moment all variables for handling data shared between functions are in global scope. The following classes will encapsulate these variables and clean up the global namespace, but they are currently under construction**

**Subject**

The subject.py class handles all subject data collected during the experiment

**Recording Manager**

The recording_manager.py class handles all recording threads and audio input settings.

**Test Manager**

The test_manager.py class handles all testing procedures. The test questions are stored in external JSON files:

    test_files/SER_questions.json

    test_files/task_1_data.json

    test_files/task_2_data.json

**EmotiBit Streamer**

The emotibit_streamer_2.py class handles all communication with the EmotiBit Oscilliscope app. The app must be running and connected to the EmotiBit device in order for data to begin streaming. The data is sent over OSC and the emotibit_streamer class starts the OSC server in a separate thread. **Please Note**: The Flask server must be run with the debug flag set to False in order for the OSC server to find an open port.

**Form Manager**

The form_manager.py class handles all functionality related to surveys and google forms including prefilling each survey with the ID of the current user. It requires the following files:

    surveys/surveys.json
    subject_data/subjects.json

