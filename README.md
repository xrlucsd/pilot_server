# Pilot Experiment Server

## A command center for running all applications during experiment

This is the active XR Lab-maintained repository.

**New Laptop Installation**

**NOTE:** The best way to install ffmpeg and Portaudio on Mac is with HomeBrew. 

To install Homebrew, run the following command in Terminal:

    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
Install portaudio with:

    brew install portaudio
Install ffmpeg with:

    brew install ffmpeg
Install postgreSQL with:

    brew install postgresql@15 

*Python Environment Setup*

**Step 1: Disable Conda.** If Conda is installed, it can interfere with the Python build and override the pyenv Python. If your terminal prompt does not start with (base) and Conda is not installed, skip to Step 2.

Stop Conda from activating automatically in new terminals:

    conda config --set auto_activate_base false
Deactivate it in your current terminal:

    conda deactivate
If you still see (base), run `conda deactivate` again until it is gone.

**Step 2: Install pyenv.**

    brew install pyenv
Run the following commands from any directory:

    touch ~/.zshrc
    echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
    echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
    echo 'eval "$(pyenv init - zsh)"' >> ~/.zshrc
This adds pyenv to ".zshrc", the file your terminal uses to configure your environment, so that it uses the right python version.
Then reload the shell by running:

    source ~/.zshrc

**Step 3: Install OpenSSL and Python 3.11.4.** Do not run a plain `pyenv install 3.11.4`. It can fail with `No available formula with the name "openssl@1.1"` or `ModuleNotFoundError: No module named '_ssl'`, because Homebrew no longer provides OpenSSL 1.1. The commands below point the build at OpenSSL 3.0 instead.

Install the libraries Python needs. Homebrew may warn that openssl@3.0 is deprecated; this is safe to ignore as long as the install finishes.

    brew install openssl@3.0 readline xz
Then copy and run the following as a single command. `--force` replaces any broken copy of 3.11.4 left by an earlier failed install.

    PYTHON_BUILD_HOMEBREW_OPENSSL_FORMULA=openssl@3.0 \
    PYTHON_CONFIGURE_OPTS="--with-openssl=$(brew --prefix openssl@3.0) --with-openssl-rpath=auto" \
    pyenv install --force 3.11.4
Confirm that it worked by running:

    pyenv versions
You should see 3.11.4 on the list.

**Step 4: Select Python 3.11.4 and create the virtual environment.**

Configure your environment to use the correct python version by running:

    pyenv global 3.11.4
Verify it worked by running:

    python --version
It should say that you are using python version 3.11.4.
Verify that Python was built with OpenSSL by running:

    python -c "import ssl; print(ssl.OPENSSL_VERSION)"
It should print a version starting with OpenSSL 3.0. If it shows an error, make sure (base) is gone and repeat Step 3.
Now create a virtual environment using that python version:

    python -m venv venv
Activate the virtual environment by running:
    
    source venv/bin/activate
Verify the environment uses python 3.11.4:

    python --version
You can now move on to installing the rest of the project dependencies.

Install all packages with:

    pip install -r requirements.txt
The Whisper models (base.en and medium.en, about 1.7 GB in total) download to models/ the first time the server starts. The Launch Subject Dashboard button is disabled until they have loaded.

Retrieve the SER model here: https://drive.google.com/drive/folders/1w3-QJEl_pzuIkiOuDUejkFp9x8Mfs4LF?usp=drive_link

Place the SER_MODEL folder at the root of the server: /pilot_server

Retrieve the video files here: https://drive.google.com/drive/folders/1nBtfuXfNhhzsi4oFjVRUnYrbLneVJI7c?usp=drive_link

Place the videos folder inside the static folder of the server: /pilot_server/static/.

**Instructions for server**

To run the server, simply open a terminal, navigate to the root folder and type:
python app.py

You should see the following result in Terminal: 
 
    * Serving Flask app 'app'
    * Debug mode: on
    WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
    * Running on http://127.0.0.1:8000
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

