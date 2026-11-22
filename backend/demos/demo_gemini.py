"""Runnable demo; live provider calls require VOYAGEAI_RUN_LIVE_TESTS=1."""
import os


def main() -> None:
    if os.getenv("VOYAGEAI_RUN_LIVE_TESTS") != "1":
        print("Live demo skipped. Set VOYAGEAI_RUN_LIVE_TESTS=1 to enable provider calls.")
        return

    from dotenv import load_dotenv
    from google import genai


    load_dotenv()

    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents="Reply with exactly: Gemini is working"
    )

    print(response.text)


if __name__ == "__main__":
    main()
