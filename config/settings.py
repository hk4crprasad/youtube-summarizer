import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "1YUY6vVtUqUQvzbSq1hen1suhxL66DWkh2tW8KwDzwN3jRWcWSWqJQQJ99AKAC5RqLJXJ3w3AAAAACOG2hZl")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://harap-m3blgd2t-westeurope.openai.azure.com/")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
TURNSTILE_SITE_KEY   = os.getenv("TURNSTILE_SITE_KEY")
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY")
# Whisper model name
WHISPER_DEPLOYMENT_NAME = "whisper"

# Temporary file storage
TEMP_DIRECTORY = os.getenv("TEMP_DIRECTORY", "temp")

# Ensure temp directory exists
os.makedirs(TEMP_DIRECTORY, exist_ok=True) 