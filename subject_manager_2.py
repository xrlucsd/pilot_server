import csv
import os
import threading
from aws_handler import AWSHandler
from datetime import datetime

class SubjectManager:
    def __init__(self) -> None:
        self._subject_id = None
        self.csv_file_path = None
        self.txt_file_path = None
        self.PID = None
        self.class_name = None
        self.headers = ['Timestamp', 'Time_Stopped', 'Event_Marker', 'Condition', 'Audio_File', 'Transcription']
        self._balance = 0
        self.data_root = "subject_data"
        self._experiment_name = None
        self._trial_name = None
        self._subject_folder = None
        self._categories = None
        # Only held in RAM and not stored.
        self._subject_first_name = None 
        self._subject_last_name = None
        self._subject_email = None
        self._subject_assigned_id = None
        # Process Audio rewrites the CSV, which must not overlap with an append.
        self.csv_lock = threading.Lock()

    @property
    def subject_assigned_id(self) -> str:
        return self._subject_assigned_id
    
    @subject_assigned_id.setter
    def subject_assigned_id(self, value: str) -> None:
        self._subject_assigned_id = value

    @property
    def subject_first_name(self) -> str:
        return self._subject_first_name
    
    @subject_first_name.setter
    def subject_first_name(self, value: str) -> None:
        self._subject_first_name = value

    @property
    def subject_last_name(self) -> str:
        return self._subject_last_name
    
    @subject_last_name.setter
    def subject_last_name(self, value: str) -> None:
        self._subject_last_name = value

    @property
    def subject_email(self) -> str:
        return self._subject_email
    
    @subject_email.setter
    def subject_email(self, value: str) -> None:
        self._subject_email = value

    @property
    def experiment_name(self) -> str:
        return self._experiment_name
    
    @experiment_name.setter
    def experiment_name(self, value: str) -> None:
        self._experiment_name = value

    @property
    def trial_name(self) -> str:
        return self._trial_name
    
    @trial_name.setter
    def trial_name(self, value: str) -> None:
        self._trial_name = value
    
    @property
    def categories(self) -> list[str]:
        return self._categories
    
    @categories.setter
    def categories(self, value: list[str]) -> None:
        self._categories = value

    @property
    def subject_folder(self) -> str:
        return self._subject_folder
    
    @subject_folder.setter
    def subject_folder(self, value: str) -> None:
        self._subject_folder = value
    
    @property
    def subject_id(self) -> str:
        return self._subject_id

    @subject_id.setter
    def subject_id(self, value: str) -> None:
        self._subject_id = value

    def set_subject(self, subject_info: dict) -> None:
        """
            Set the subject's name, ID, and email, PID (if any), class name (if any) and initialize the CSV file.
            Args:
                subject_info (dict): Dictionary containing the subject's name, ID, and email.
                Expected format: {"name": str, "id": str, "email": str, "PID": str, "class_name": str} 
            Returns:
                None
        """
        self.subject_id = subject_info["id"]
        self.PID = subject_info["PID"]
        self.class_name = subject_info["class_name"]
        self.subject_assigned_id = subject_info["assigned_id"]

        if not self.experiment_name or not self.trial_name:
            raise ValueError("Experiment name and trial name must be set before setting the subject.")
        
        else:
            folder_name = f"{self.subject_assigned_id}_{datetime.now().isoformat()}_{self.subject_id}"
            self.subject_folder = os.path.join(self.data_root, self.experiment_name, self.trial_name, folder_name)

            if not os.path.exists(self.subject_folder):
                os.makedirs(self.subject_folder)

            current_date = datetime.now().strftime("%Y-%m-%d")
            csv_filename = f"{current_date}_{self.experiment_name}_{self.trial_name}_{self.subject_id}.csv"
            self.csv_file_path = os.path.join(self.subject_folder, csv_filename)

            # DEBUG
            print("Subject folder set: ", self.subject_folder)
            print("Subject data csv set: ", self.csv_file_path)
            
            self.create_csv(self.csv_file_path)
    
    def create_csv(self, csv_file_path: str) -> None:
        if not os.path.exists(csv_file_path):
            with open(csv_file_path, mode='w', newline='', encoding='utf-8') as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow([f"Experiment Name: {self.experiment_name}"])
                writer.writerow([f"Trial Name: {self.trial_name}"])
                writer.writerow([f"Subject ID: {self.subject_id}"])
                writer.writerow([f"Categories: {self.categories}"])
                writer.writerow([f"PID: {self.PID}"])
                writer.writerow([f"Class Name: {self.class_name}"])  
                writer.writerow(self.headers)  

    def append_data(self, data: dict) -> None:
        """
        Append data to the main CSV file, ignoring columns that are not relevant to the current data collection.
        Args:
            data (dict): Dictionary containing the data to be appended, where keys are column names and values are the corresponding data.
            Expected format: {'Timestamp': str, 'Event_Marker': str, 'Transcription': str, 'SER_Emotion': str, 'SER_Confidence': str}
        """
        metadata_rows = 6

        with self.csv_lock:
            try:
                with open(self.csv_file_path, mode='r', newline='', encoding='utf-8') as csvfile:
                    reader = csv.reader(csvfile)
                    file_contents = list(reader)

                    if len(file_contents) < metadata_rows + 1:
                        print("Metadata rows not found. Enter subject information first.")
                        return

            except FileNotFoundError:
                print("CSV file not found. Enter subject information first.")
                return

            filtered_data = {key: value for key, value in data.items() if key in self.headers and value != ""}
            row = [filtered_data.get(header, "") for header in self.headers]

            # DEBUG
            print(row)

            with open(self.csv_file_path, mode='a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(row)

        print(f"Data has been successfully appended to {self.csv_file_path}.")

    def update_transcription(self, csv_file_path: str, audio_file: str, transcription: str) -> None:
        """
        Fill in the Transcription cell of the row for an audio file.
        Args:
            csv_file_path (str): The participant's CSV, captured when the recording was queued.
            audio_file (str): The Audio_File value identifying the row.
            transcription (str): The text to store.
        """
        with self.csv_lock:
            with open(csv_file_path, mode='r', newline='', encoding='utf-8') as csvfile:
                rows = list(csv.reader(csvfile))

            audio_column = self.headers.index('Audio_File')
            transcription_column = self.headers.index('Transcription')
            header_row = rows.index(self.headers)
            matches = [row for row in rows[header_row + 1:] if len(row) == len(self.headers) and row[audio_column] == audio_file]

            if not matches:
                print(f"No row found for {audio_file}; transcription not stored.")
                return

            for row in matches:
                row[transcription_column] = transcription

            # Replace the file in one step so a crash cannot leave a partial CSV.
            temp_path = f"{csv_file_path}.tmp"
            with open(temp_path, mode='w', newline='', encoding='utf-8') as csvfile:
                csv.writer(csvfile).writerows(rows)
            os.replace(temp_path, csv_file_path)

        print(f"Transcription stored for {audio_file}.")

    def load_data(self) -> list[dict]:
        """Load and return all data from the CSV file."""
        if not self.csv_file_path:
            raise ValueError("Subject has not been set. Call 'set_subject' first.")
        
        with open(self.csv_file_path, mode='r', newline='', encoding='utf-8') as csv_file:
            reader = csv.DictReader(csv_file)
            return list(reader)

    def reset_subject(self) -> None:
        """Reset the subject details and clear the CSV file reference."""
        self.subject_id = None
        self.csv_file_path = None