from config.gemini_config import get_gemini_client, get_gemini_model

def main():
    try:
        client = get_gemini_client()
        model = get_gemini_model()

        print("Gemini client initialized successfully!")
        print("Configured model:", model)

        response = client.models.generate_content(
            model=model,
            contents="Reply with exactly: Gemini connection successful"
        )

        print("API response:", response.text)

    except Exception as error:
        print("Gemini connection failed.")
        print("Error:", error)

if __name__ == "__main__":
    main()