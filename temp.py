import subprocess
import os

def ppt_to_pdf(input_file, output_dir):
    """
    Convert a PowerPoint file to PDF using LibreOffice.
    
    :param input_file: Path to the .pptx file
    :param output_dir: Directory where the PDF will be saved
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"File {input_file} does not exist")
    
    if not os.path.isdir(output_dir):
        raise NotADirectoryError(f"{output_dir} is not a valid directory")
    
    # LibreOffice command to convert to PDF
    command = [
        "libreoffice",
        "--headless",
        "--convert-to", "pdf",
        "--outdir", output_dir,
        input_file
    ]
    
    subprocess.run(command, check=True)
    print(f"Converted {input_file} to PDF and saved in {output_dir}")

# Example usage
input_pptx = "temp.pptx"
output_directory = "/home/qu-user1/Github/QuCreate-airflow"
ppt_to_pdf(input_pptx, output_directory)
