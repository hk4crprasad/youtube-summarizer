import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

# Whisper model name
WHISPER_DEPLOYMENT_NAME = "whisper"

# Temporary file storage
TEMP_DIRECTORY = os.getenv("TEMP_DIRECTORY", "temp")

# Ensure temp directory exists
os.makedirs(TEMP_DIRECTORY, exist_ok=True)

# Whisper settings (if using local Whisper)
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")  # Options: tiny, base, small, medium, large

# Azure Speech settings
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")

# Azure Storage settings
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "youtube-transcripts")

# MongoDB settings
MONGODB_URI = os.getenv("MONGODB_URI")
SECRET_KEY = os.getenv("SECRET_KEY") 