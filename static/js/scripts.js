document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".toggle").forEach(button => {
        const workflowRow = button.closest(".workflow-step") || button;

        if (workflowRow.classList.contains("workflow-step-toggle")) {
            let initialDiv = workflowRow.nextElementSibling;
            while (initialDiv && initialDiv.tagName !== "DIV") {
                initialDiv = initialDiv.nextElementSibling;
            }
            workflowRow.setAttribute("aria-expanded", String(initialDiv?.style.display !== "none"));
            button.setAttribute("aria-expanded", String(initialDiv?.style.display !== "none"));
        }

        button.addEventListener("click", function () {
            const currentWorkflowRow = this.closest(".workflow-step") || this;
            let nextDiv = currentWorkflowRow.nextElementSibling;

            while (nextDiv && nextDiv.tagName !== "DIV") {
                nextDiv = nextDiv.nextElementSibling;
            }

            if (nextDiv) {
                // Toggle between display: none and display: block
                const isOpening = nextDiv.style.display === "none";
                nextDiv.style.display = isOpening ? "block" : "none";
                if (currentWorkflowRow.classList.contains("workflow-step-toggle")) {
                    currentWorkflowRow.setAttribute("aria-expanded", String(isOpening));
                    this.setAttribute("aria-expanded", String(isOpening));
                }
            }
        });
    });
});

function processAudioFiles(statusElement, pathElement){
    fetch('/process_audio_files', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log(data.message);
        statusElement.style.display = 'block';
        statusElement.innerText = data.message;
        pathElement.style.display = 'block';
        pathElement.innerText = `Transcription/SER CSV location: ${data.path}`;
    })
    .catch(error => {
        console.error('Error:', error);
        statusElement.style.display = 'block';
        statusElement.innerText = "Error processing audio files.";
    });
}

function completeTask(taskId, button) {
    if (button) {
        button.disabled = true;
    }

    return fetch('/complete_task', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'},
        body: JSON.stringify({ task_id: taskId, action: 'complete' })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Unable to complete task (${response.status})`);
        }
        console.log(`Task ${taskId} completed`);
        if (button && typeof markTaskCompleted === 'function') {
            markTaskCompleted(button, taskId);
        }
        return response.json();
    })
    .catch(error => {
        if (button) {
            button.disabled = false;
        }
        console.error('Error:', error);
        return null;
    });
}

function reopenTask(taskId) {
    return fetch('/complete_task', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'},
        body: JSON.stringify({ task_id: taskId, action: 'reopen' })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Unable to reopen task (${response.status})`);
        }
        console.log(`Task ${taskId} reopened`);
        return response.json();
    });
}

function sendStatus() {
    fetch('/status_update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'Subject is ready' })
    });
}

function updateCondition(parentDiv, event) {
    const selectElement = document.querySelector(`#${parentDiv} select`);
    const selectedCondition = selectElement.value;
    localStorage.setItem('currentEventMarker', event);
    localStorage.setItem('currentCondition', selectedCondition);
    console.log(selectedCondition);
    console.log(event);
}

function setCondition(condition){
    fetch('/set_condition', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'condition': condition
        })
    })
    .then(response => response.json())
    .then(data => {
        console.log(data.status);
    })
    .catch(error => console.error('status:', error));
}

function setEventMarker(eventMarker){
    fetch('/set_event_marker', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'event_marker': eventMarker
        })
    })
    .then(response => response.json())
    .then(data => {
        console.log(data.status);
    })
    .catch(error => console.error('status:', error));
}

function recordTaskAudio(eventMarker, condition, action, question, divID){
    fetch('/record_task_audio', { method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'event_marker': eventMarker,
            'condition': condition,
            'action': action,
            'question': question
        })
     })
    .then(response => response.json())
    .then(data => {
        if (data.message === 'Error starting recording.'|| data.message === 'Invalid action.') {
            console.error(data.message);
            divID.style.display = 'block';
            divID.innerText = `Please stop playback... ${data.message}`;
            return;
        } else {
            console.log(data.message);
            divID.style.display = 'block';
            divID.innerText = data.message;
        }
    })
    .catch(error => {
        console.error('Error:', error);
        divID.style.display = 'block';
        divID.innerText = `Please stop playback... ${error}`;
    });
}
    
async function startRecording() {
    try {
        const response = await fetch('/start_recording', {
            method: 'POST'
        });
        const data = await response.json();
        console.log("Recording started", data.status);
    } catch (error) {
        console.error('Recording Error:', error);
    }
}

async function stopRecording(){
    try{
        const response = await fetch('/stop_recording', {
            method: 'POST'
        });
        const data = await response.json();
        console.log(data.status);
    } catch (error) {   
        console.error('Recording Error:', error);
    }
}

async function processSERTest() {
    try {
        const response = await fetch('/process_ser_test', {
            method: 'POST'
        });
        const data = await response.json();
        console.log(data.status);
    } catch (error) {
        console.error('SER Test Error:', error);
    }
}

function getSERQuestion(){
    fetch('/get_ser_question', {
        method: 'GET'
    })
    .then(response => response.json())
    .then(data => {
        return data.question; 
    })
    .catch(error => {
        console.error('Error fetching SER question:', error);
        return "Couldn't get question"; 
    });
}

async function submitSERAnswer(){
    fetch("/process_ser_answer", { method: "POST" })
        .then(response => {
            return response.json();
        })
        .then(data => {
            if (data.status === 'error') {
                document.getElementById("status").innerHTML = data.message;
                document.getElementById("status").style.display = "block";
                document.getElementById("status").disabled = false;
            } else {
                document.getElementById("status").innerHTML = data.message;
                document.getElementById("status").style.display = "block";
                document.getElementById("status").disabled = false;
            }
        })
        .catch(error => {
            console.error('Error processing SER answer:', error);
            document.getElementById("status").innerHTML = "Error occurred while processing the answer.";
            document.getElementById("status").style.display = "block";
            document.getElementById("status").disabled = false;
        });
}

function setDevice() {
    const audioDevices = document.getElementById('audioDevices');
    const selectedDeviceIndex = audioDevices.value;
    console.log('Selected Device Index:');
    console.log(selectedDeviceIndex);
    fetch('/set_device', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({device_index: selectedDeviceIndex})
    })
    .then(response => response.json())
    .then(data => {
            console.log(data.message);
    })
    .catch(error => alert('Error:' + error));
}

function toggleVis(divID) {
    const element = document.getElementById(divID);
    if (element.style.display === "none") {
        element.style.display = "block";
        element.disabled = false;
    } else {
        element.style.display = "none";
        element.disabled = true;
    }
}

function shutdownServer(){
    fetch('/shutdown', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
            console.log(data.message);
    })
    .catch(error => alert('Error:' + error));
}

function fetchAudioDevices() {
    fetch('/get_audio_devices')
        .then(response => response.json())
        .then(data => {
            console.log(data);
            const audioDevicesDropdown = document.getElementById('audioDevices');
            
            // Clear existing options
            audioDevicesDropdown.innerHTML = '';

            // Populate dropdown with devices
            data.forEach(device => {
                const option = document.createElement('option');
                option.value = device.index;
                option.text = device.name;
                audioDevicesDropdown.appendChild(option);
            });

            // If only one device is available, auto-select it
            if (data.length === 1) {
                setDevice(); // Automatically sets the single available device
            }
        })
        .catch(error => alert('Error: ' + error));
}

async function startEmotibit(){
    fetch('/start_emotibit', {
            method: 'POST'
        })
        .then (response => {
            return response.json().then(data => {
                if (!response.ok) {
                    // Throw with server-provided error message
                    throw new Error(data.message || 'Unknown error');
                }
                return data;
            });
        })
        .then(data => {
            console.log(data.message);
            emotibitStatus.forEach(status => {  
                status.style.display = 'block';
                status.innerText = data.message;
            });
        })
        .catch(error => {
            console.error('Error starting EmotiBit stream:', error);
            emotibitStatus.forEach(status => {
                status.style.display = 'block';
                status.innerText = error.message || 'Error starting EmotiBit stream.';
            });
        });
}

function playBeep() {
    const beepContext = new AudioContext();
    const oscillator = beepContext.createOscillator();
    const gainNode = beepContext.createGain();
    oscillator.type = 'sine'; 
    oscillator.frequency.setValueAtTime(500, beepContext.currentTime);
    gainNode.gain.setValueAtTime(0.07, beepContext.currentTime);
    oscillator.connect(gainNode);
    gainNode.connect(beepContext.destination);
    oscillator.start();
    setTimeout(() => {
        oscillator.stop();
    }, 300); 
}
