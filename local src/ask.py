import os

from google import genai

from retrieve_rerank import retrieve_and_rerank


MODEL_NAME = "gemini-3.5-flash"


def build_context(candidates):
    context_parts = []

    for index, candidate in enumerate(candidates, start=1):
        metadata = candidate["metadata"]

        context_parts.append(
            f"""[Source {index}]
Subject: {metadata["subject"]}
From: {metadata["from_email"]}
Date: {metadata["date"]}
Chunk ID: {candidate["chunk_id"]}

{candidate["document"]}"""
        )

    return "\n\n---\n\n".join(context_parts)


def build_prompt(question, context):
    return f"""You are answering questions about the user's Gmail inbox.

Use only the email sources provided below.
If the sources do not contain the answer, say that you could not find the answer in the retrieved emails.
Do not guess.
Cite sources using bracket numbers like [1] or [2].

Question:
{question}

Email sources:
{context}

Answer:"""


def print_sources(candidates):
    print("\nSources:")

    for index, candidate in enumerate(candidates, start=1):
        metadata = candidate["metadata"]

        print(f"{index}. {metadata['subject']}")
        print(f"   From: {metadata['from_email']}")
        print(f"   Date: {metadata['date']}")
        print(f"   Chunk ID: {candidate['chunk_id']}")
        print(f"   Rerank score: {candidate['score']}")


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("Missing GEMINI_API_KEY environment variable.")
        
        raise SystemExit

    question = input("Ask a question about your inbox: ").strip()

    if question == "":
        print("Invalid. Please enter a question.")
        raise SystemExit

    candidates = retrieve_and_rerank(question)
    context = build_context(candidates)
    prompt = build_prompt(question, context)

    client = genai.Client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )

    print("\nAnswer:")
    print(response.text)
    print_sources(candidates)


if __name__ == "__main__":
    main()
