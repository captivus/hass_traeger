import base64
import glob
import json
import os
import readline


class CHLSJReader:
    def __init__(self, file_path, decode_base64=False):
        self.file_path = file_path
        self.data = None
        self.decode_base64 = decode_base64

    def read_file(self):
        """
        Reads the .chlsj file and stores the data in the `data` attribute.
        """
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                self.data = file.read()
        except Exception as e:
            print(f"Error reading file: {e}")
            raise

    def parse_data(self):
        """
        Parses the raw data read from the .chlsj file into a structured format.
        """
        try:
            self.data = json.loads(self.data)  # Assuming .chlsj is a JSON-like format
            if self.decode_base64:
                self.data = self._decode_base64_in_data(self.data)
        except json.JSONDecodeError as e:
            print(f"Error parsing data: {e}")
            raise

    def _decode_base64_in_data(self, data):
        """
        Recursively decodes base64 encoded strings in the data and adds a "decoded" key.
        """
        if isinstance(data, dict):
            new_data = {}
            for key, value in data.items():
                new_data[key] = self._decode_base64_in_data(value)
                if (
                    isinstance(value, dict)
                    and "encoding" in value
                    and value["encoding"] == "base64"
                ):
                    new_data[key]["decoded"] = self._decode_base64_string(
                        value.get("encoded")
                    )
            return new_data
        elif isinstance(data, list):
            return [self._decode_base64_in_data(item) for item in data]
        else:
            return data

    def _decode_base64_string(self, encoded_str):
        """
        Decodes a base64 encoded string. If the decoding fails, returns the original string.
        """
        try:
            decoded_bytes = base64.b64decode(encoded_str)
            decoded_str = decoded_bytes.decode("utf-8")
            return decoded_str
        except (base64.binascii.Error, UnicodeDecodeError):
            return encoded_str

    def convert_to_json(self, output_file_path):
        """
        Converts the parsed data to a JSON file.

        Parameters:
        output_file_path (str): The path where the JSON file will be saved.
        """
        if self.data is None:
            print("No data to convert. Ensure that the file is read and parsed first.")
            return

        try:
            with open(output_file_path, "w", encoding="utf-8") as json_file:
                json.dump(self.data, json_file, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error writing JSON file: {e}")
            raise

    def process_file(self, output_file_path):
        """
        Reads, parses, and converts the .chlsj file to JSON in one step.

        Parameters:
        output_file_path (str): The path where the JSON file will be saved.
        """
        self.read_file()
        self.parse_data()
        self.convert_to_json(output_file_path)


# Example usage
if __name__ == "__main__":
    # allow user to enter filename with tab completion
    def complete(text, state):
        return (glob.glob(text + "*") + [None])[state]

    readline.set_completer_delims("\t")
    readline.parse_and_bind("tab: complete")
    readline.set_completer(complete)

    input_filename = input("Enter the filename: ")
    # add current working directory to filename
    input_filename = f"{os.getcwd()}/{input_filename}"

    # create output filename as input filename with '_output.json' appended
    output_filename = f"{os.path.splitext(input_filename)[0]}_output.json"

    # configure output file to be in same directory as input file
    output_filename = (
        f"{os.path.dirname(input_filename)}/{os.path.basename(output_filename)}"
    )

    # reader = CHLSJReader("example.chlsj")
    # reader.process_file("output.json")

    # output without base64 decoding
    reader = CHLSJReader(input_filename)
    reader.process_file(output_filename)

    # output with base64 decoding
    reader = CHLSJReader(input_filename, decode_base64=True)
    reader.process_file(f"{os.path.splitext(output_filename)[0]}_decoded.json")

    print(f"Converted {input_filename} to {output_filename}")
    print(
        f"Converted {input_filename} with base64 decoding to {os.path.splitext(output_filename)[0]}_decoded.json"
    )
