
import json
import os
import re
import csv

class FormManager:
    def __init__(self) -> None:
        self._surveys_file = "surveys/surveys.json"
        self._added_surveys_file = "surveys/added_surveys.json"
        self._subjects_file = "subject_data/subjects.json"
        self._surveys = self.load_surveys()
        self._formatted_surveys = []
        self._added_surveys = []
        self.initialize_subjects_file()
        print("Form Manager initialized...")
        print("Form Manager's surveys file set to 'surveys/surveys.json'")

    def initialize_subjects_file(self) -> None:
        """Create an empty subjects file if one doesn't exist. Never overwrites an existing file."""
        if os.path.exists(self._subjects_file):
            return

        print(f"{self._subjects_file} does not exist. Creating new file...")
        os.makedirs(os.path.dirname(self._subjects_file), exist_ok=True)
        with open(self._subjects_file, 'w') as file:
            json.dump({"subjects": {}}, file, indent=4)

    @property
    def added_surveys(self) -> list:
        return self._added_surveys
    
    @added_surveys.setter
    def added_surveys(self, added_surveys) -> None:
        self._added_surveys = added_surveys

    @property
    def embed_codes(self) -> list:
        return self._embed_codes
    
    @embed_codes.setter
    def embed_codes(self, embed_codes) -> None:
        self._embed_codes = embed_codes

    @property
    def surveys(self) -> list:
        return self._surveys
    
    @surveys.setter
    def surveys(self, surveys) -> None:
        self._surveys = surveys
    
    @property
    def formatted_surveys(self) -> list:
        return self._formatted_surveys
    
    @formatted_surveys.setter
    def formatted_urls(self, formatted_urls) -> None:
        self._formatted_urls = formatted_urls
    
    @formatted_surveys.deleter
    def formatted_surveys(self) -> None:
        self._formatted_surveys = []

    def add_survey(self, survey_name, survey_url) -> str:
        """
        Adds a survey to the list of surveys.
        Current functionality is a modification of the original function to store survey links in a JSON file.
        If the old functionality is needed, comment out the blocks of code that are marked with a comment and
        uncomment everything else.  
        """
        survey_data = self.load_added_surveys()
        if survey_data is None:
            print("Survey file missing.")
            return("Survey file missing.")

        survey = {
            "name": survey_name,
            "url": survey_url
        }

        if survey not in survey_data:
            survey_data.append(survey)

            if self._added_surveys_file:
                with open(self._added_surveys_file, "w") as file:
                    json.dump({"surveys": survey_data}, file, indent=4)
                return "Success"
            else:
                print("Survey already exists.")
                return "Survey already exists."
    
    def find_survey_response(self, input_file, output_file, search_email) -> bool:
        with open(input_file, mode="r", newline="", encoding="utf-8") as infile:
            reader = csv.reader(infile)
            headers = next(reader)
            
            try:
                email_index = headers.index("Email")
            except ValueError:
                print("Email column not found.")
                return False
            
            matching_row = None
            for row in reader:
                email_value = row[email_index].strip().lower()
                if self.is_valid_email(email_value) and email_value == search_email:
                    matching_row = row
                    break
            
            if matching_row is None:
                print(f"Survey response for {search_email} not found.")
                return False
            else:
                with open(output_file, mode="w", newline="", encoding="utf-8") as outfile:
                    writer = csv.writer(outfile)
                    writer.writerow(headers)
                    writer.writerow(matching_row)
                    print(f"Survey response for {search_email} found. Writing to {output_file}")
                    return True
            
    def is_valid_email(self, email):
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return re.match(pattern, email) is not None

    def survey_exists(self, survey_name) -> bool:
        surveys = self.load_surveys()
        for survey in surveys:
            if survey["name"] == survey_name:
                return True
        return False
    
    def clean_string(self, value) -> str:
        outstring = value.lower().replace(' ', '_').strip()
        outstring = re.sub(r"[^a-zA-Z0-9_\-]", "", outstring)
        return outstring
    
    def get_survey_url(self, name):
        """
        Retrieve the URL of a survey by its name.
        Args:
            name (str): The name of the survey to find.
        Returns:
            str: The URL of the survey if found, otherwise "Survey not found".
        """
        surveys = self.load_surveys()
        survey = next((s for s in surveys if s["name"] == name), None)
        if not survey:
            return "Survey not found"
        else:
            return survey["url"]

    def remove_survey(self, survey_name) -> None:
        for survey in self._surveys:
            if survey["name"] == survey_name:
                self._surveys.remove(survey)

        with open(self._surveys_file, "w") as file:
            json.dump({"surveys": self._surveys}, file, indent=4)

    def customize_form_url(self, url, subject_id) -> str:
        """
        Replaces 'Sample+ID' in a Google Forms URL with the provided subject_id.
        Parameters:
            url (str): The Google Forms URL containing 'Sample+ID' as a placeholder.
            subject_id (str): The value to replace 'Sample+ID'.
        Returns:
            str: The updated URL with 'Sample+ID' replaced by subject_id.
        """
        if not url.strip(): 
            return url

        subject_id = subject_id.replace(" ", "+")
        updated_url = url.replace("Sample+ID", subject_id)

        return updated_url

    def autofill_forms(self, subject_id) -> None:
        formatted_surveys = []
        if self.surveys:
            for survey in self.surveys:
                url = self.customize_form_url(survey["url"], subject_id)
                formatted_survey = {
                    "name": survey["name"],
                    "url": url
                }
                formatted_surveys.append(formatted_survey)

            self.surveys = formatted_surveys
            del self.formatted_surveys
        else:
            raise ValueError("No surveys to autofill.")
    
    def load_added_surveys(self) -> list:
        if not os.path.exists(self._added_surveys_file):
            print("surveys/added_surveys.json does not exist. Adding new file...")
            with open(self._added_surveys_file, "w") as file:
                json.dump({"added_surveys": []}, file)
    
            with open(self._added_surveys_file, "r") as file:
                added_surveys = json.load(file)
                surveys = added_surveys.get("added_surveys", [])
                return surveys
        else:
            with open(self._added_surveys_file, "r") as file:
                print("Loading added surveys...")
                added_surveys = json.load(file)
                surveys = added_surveys.get("added_surveys", [])
                return surveys
            
    def load_surveys(self) -> list:
        if not os.path.exists(self._surveys_file):
            print("surveys/surveys.json does not exist.")
            return []
        else:
            with open(self._surveys_file, "r") as file:
                survey_data = json.load(file)
                surveys = survey_data.get("surveys", [])
                return surveys
            
    def get_survey_url(self, survey_name: str) -> str:
        surveys = self.load_surveys()
        added_surveys = self.load_added_surveys()
        for survey in surveys + added_surveys:
            if survey["name"] == survey_name:
                return survey["url"]
    
        return "not found"
    
    def get_custom_url(self, survey_name: str, subject_id: str) -> str:
        """
        Retrieves the URL for the given survey and customizes it with the subject's name and ID.

        Parameters:
            survey_name (str): The name of the survey to retrieve the URL for.
            subject_id (str): The ID of the subject to be inserted into the URL.

        Returns:
            str: The customized URL for the specified survey.
        """
        survey_url = self.get_survey_url(survey_name)

        if survey_url is None: 
            return f"Survey with name '{survey_name}' not found."  
        
        return self.customize_form_url(survey_url, subject_id)
    
    def get_subject_name(self, email: str) -> str:
        with open(self._subjects_file, 'r') as file:
            subject_objs = json.load(file)
            for key, value in subject_objs['subjects'].items():
                if key == email:  # Email is now the key, no need to check inside the value
                    return value['first_name'], value['last_name']
                
        return None, None
      
    def add_to_subject_ids(self, subject_id, first_name, last_name, email) -> None:
        """
        Add the subject's ID, first name, last name, and email to the subject IDs file.
        Args:
            subject_id (str): The subject's unique ID.
            first_name (str): The subject's first name.
            last_name (str): The subject's last name.
            email (str): The subject's email address.
        """

        file_path = self._subjects_file

        self.initialize_subjects_file()
        with open(file_path, 'r') as file:
            subject_objs = json.load(file)

        if "subjects" not in subject_objs:
            subject_objs["subjects"] = {}
            print("Subjects key not found. Creating new key.")

        if email in subject_objs["subjects"]:
            return

        subject_objs["subjects"][email] = {
            "subject_id": subject_id,
            "first_name": first_name,
            "last_name": last_name
        }

        with open(file_path, 'w') as file:
            json.dump(subject_objs, file, indent=4)
            return 