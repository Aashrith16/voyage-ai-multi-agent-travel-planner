from dotenv import load_dotenv
from google import genai


load_dotenv()

client = genai.Client()

response = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents="Reply with exactly: Gemini is working"
)

print(response.text)