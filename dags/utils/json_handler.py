import json

class JSONHandler:
    """
    This class is used to handle the configuration file for the chain.

    Input: filepath (str) - the path to the configuration file

    Attributes:
    filepath (str) - the path to the configuration file
    config (dict) - the configuration file as a dictionary

    Methods:
    get_config() - returns the configuration file as a dictionary
    set_config(config) - sets the configuration file to the input dictionary
    write_config(filepath) - writes the configuration file to the input filepath

    """
    def __init__(self, filepath):
        # Initialize the JSONHandler object with the input filepath
        self.filepath = filepath
        self.config = json.load(open(filepath))

    def get_config(self):
        # Get the configuration file as a dictionary
        return self.config
    
    def set_config(self, json):
        # Set the configuration file to the input dictionary
        self.config = json

    def update_config(self, key, value):
        # Update the configuration file with the input key and value
        self.config[key] = value
    
    def write_config(self, filepath=None):
        # Write the configuration file to the input filepath
        if filepath is None:
            filepath = self.filepath
        with open(filepath, 'w') as file:
            json.dump(self.config, file, indent=4)

    def __del__(self):
        # Write the configuration file to the input filepath when the object is deleted
        if self.config != {} or self.config is not None:
            self.write_config(self.filepath)