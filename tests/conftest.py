"""Never consume a developer's live credentials during automated tests."""
import os

os.environ['DEEPGRAM_API_KEY'] = ''
os.environ['GROQ_API_KEY'] = ''
