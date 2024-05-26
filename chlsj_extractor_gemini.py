import json
import base64
import os
import glob
import readline

from nbformat import convert

class NetworkLogExtractor:
    """
    Extracts and processes network log data from files in a specific format.
    """

    def __init__(self, file_path):
        """
        Initializes the extractor with the file path.

        Args:
            file_path (str): The path to the network log file.
        """
        self.file_path = file_path
        self.log_entries = []

    def extract_data(self):
        """Extracts and processes the log data from the file."""
        with open(self.file_path, 'r') as file:
            log_data = json.load(file)  # Load the entire JSON content

            for entry in log_data:  # Iterate over dictionaries in the list
                try:
                    # Decode base64-encoded body content (if present)
                    if "body" in entry["request"] and "encoded" in entry["request"]["body"]:
                        entry["request"]["body"]["decoded"] = base64.b64decode(
                            entry["request"]["body"]["encoded"]
                        ).decode('utf-8', errors='replace')

                    self.log_entries.append(entry)
                except json.JSONDecodeError:
                    print(f"Warning: Skipping invalid JSON entry: {entry}")
        return self.log_entries

    def get_entries_by_status(self, status):
        """
        Filters log entries based on a specific status.

        Args:
            status (str): The status to filter by.

        Returns:
            list: A list of log entries matching the given status.
        """
        return [entry for entry in self.log_entries if entry.get('status') == status]

    # Add more filtering/processing methods as needed


def convert_to_json(input_file, output_file):
    """Converts a file with concatenated JSON objects to valid JSON format.

    Args:
        input_file (str): Path to the input file.
        output_file (str): Path to the output JSON file.
    """

    with open(input_file, 'r') as infile:
        data = infile.read()

    # Split the concatenated JSON objects
    json_objects = data.strip('[]').split('},')

    # Fix any missing closing brackets and parse each object
    parsed_objects = []
    for obj in json_objects:
        if not obj.endswith('}'):
            obj += '}'
        parsed_objects.append(json.loads(obj))

    # Write the parsed objects as a list to the output file
    with open(output_file, 'w') as outfile:
        json.dump(parsed_objects, outfile, indent=4)


if __name__ == "__main__":
    # convert input file to JSON
        
    # allow user to enter filename with tab completion
    def complete(text, state):
        return (glob.glob(text+'*')+[None])[state]

    readline.set_completer_delims('\t')
    readline.parse_and_bind("tab: complete")
    readline.set_completer(complete)

    input_filename = input("Enter the filename: ")
    # add current working directory to filename
    input_filename = f"{os.getcwd()}/{input_filename}"

    # create output filename based on input filename prefix
    output_filename = input_filename.split('.')[0] + '_output.json'
    # add input file directory to output filename
    output_filename = f"{os.path.dirname(input_filename)}/{output_filename}"
    
    convert_to_json(input_filename, output_filename)
    print(f"Converted {input_filename} to {output_filename}")


# if __name__ == "__main__":
#     # create extractor instance and prompt user for filename
    
#     # allow user to enter filename with tab completion
#     def complete(text, state):
#         return (glob.glob(text+'*')+[None])[state]

#     readline.set_completer_delims('\t')
#     readline.parse_and_bind("tab: complete")
#     readline.set_completer(complete)

#     filename = input("Enter the filename: ")
#     # add current working directory to filename
#     filename = f"{os.getcwd()}/{filename}"

#     extractor = NetworkLogExtractor(filename)
#     log_data = extractor.extract_data()

#     # Get all completed entries
#     completed_entries = extractor.get_entries_by_status('COMPLETE')
#     print(completed_entries)