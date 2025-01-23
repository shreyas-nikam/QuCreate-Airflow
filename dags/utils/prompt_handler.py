from utils.prompts import prompts

class PromptHandler:
    """
    Class to handle prompts

    Attributes:
    prompts (dict) - dictionary containing prompts
    file_path (str) - the path to the prompts file

    Methods:
    get_prompt(prompt_name, **kwargs) - get the prompt from the dictionary
    update_prompt(prompt_name, prompt) - update the prompt in the dictionary
    write_prompts() - write the prompts to the file
    """
    def __init__(self, file_path="prompts.py", prompts=prompts):
        # Initialize the PromptHandler object with the input prompts and file path
        self.file_path = file_path
        self.prompts = prompts


    def get_prompt(self, prompt_name):
        # Get the prompt from the dictionary
        return self.prompts[prompt_name]
    
    def update_prompt(self, prompt_name, prompt):
        # Update the prompt in the dictionary
        self.prompts[prompt_name] = prompt
    
    def write_prompts(self):
        # Write the prompts to the file
        with open(self.file_path, 'w') as file:
            file.write('prompts = {')
            for key, value in self.prompts.items():
                file.write(f'    "{key}": """{value}""",\n')
            file.write('}\n')
            file.write("\ndef get_prompts():\n\treturn prompts\n")
    
    def __del__(self):
        # self.write_prompts()
        pass
