import glob
import json
import os
import glob
import readline

class ChlsjExtractor:
    def __init__(self, file_path):
        self.file_path = file_path
        self.data = None

    def load_data(self):
        # Read the .chlsj file
        with open(self.file_path, 'r') as file:
            self.data = json.load(file)

    def extract_data(self):
        if self.data is None:
            raise ValueError("Data not loaded. Call load_data() first.")

        extracted_data = []

        # Extract data from the file
        for document in self.data:
            index = document['index']
            source = document['source']
            content = document['document_content']

            # Extract specific data from each request/response
            for item in json.loads(content):
                status = item['status']
                method = item['method']
                host = item['host']
                path = item['path']

                # Extract request data
                request_body = item['request']['body']['encoded']
                request_headers = item['request']['header']['headers']

                # Extract response data
                response_body = item['response']['body']['encoded']

                # Create a dictionary with extracted data
                entry = {
                    'index': index,
                    'source': source,
                    'status': status,
                    'method': method,
                    'host': host,
                    'path': path,
                    'request_body': request_body,
                    'request_headers': request_headers,
                    'response_body': response_body
                }

                extracted_data.append(entry)

        return extracted_data
    
if __name__ == "__main__":
    # create extractor instance and prompt user for filename
    
    # allow user to enter filename with tab completion
    def complete(text, state):
        return (glob.glob(text+'*')+[None])[state]

    readline.set_completer_delims('\t')
    readline.parse_and_bind("tab: complete")
    readline.set_completer(complete)

    filename = input("Enter the filename: ")
    # add current working directory to filename
    filename = f"{os.getcwd()}/{filename}"
    extractor = ChlsjExtractor(filename)


    #extractor = ChlsjExtractor('file.chlsj')
    extractor.load_data()
    extracted_data = extractor.extract_data()

    # Process the extracted data
    for entry in extracted_data:
        print(f"Document Index: {entry['index']}")
        print(f"Source: {entry['source']}")
        print(f"Status: {entry['status']}")
        print(f"Method: {entry['method']}")
        print(f"Host: {entry['host']}")
        print(f"Path: {entry['path']}")
        print(f"Request Body: {entry['request_body']}")
        print(f"Request Headers: {entry['request_headers']}")
        print(f"Response Body: {entry['response_body']}")
        print("---")