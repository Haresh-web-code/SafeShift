from app.llm import generate_text


def main():
    prompt = """
    You are SafeShift, a workplace safety assistant.

    Explain three important safety checks
    before operating an industrial machine.

    Keep the answer short.
    """

    answer = generate_text(prompt)

    print("\n--- GEMINI RESPONSE ---\n")
    print(answer)


if __name__ == "__main__":
    main()