import sqlite3


DB_PATH = "data/gmailrag.sqlite3"
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 300
#2000 characters per chunk. If exceeds 2000 char per email, split and apply 300 overlap.

def build_email_text(email):
    parts = [
        f"Subject: {email['subject']}",
        f"From: {email['from_email']}",
        f"Date: {email['date']}",
        "",
        email["body"],
    ]

    return "\n".join(parts).strip()


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = end - overlap

    return chunks


def main():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("DELETE FROM email_chunks")

    cursor.execute(
        """
        SELECT
            message_id,
            thread_id,
            from_email,
            subject,
            date,
            body
        FROM emails
        """
    )

    emails = cursor.fetchall()
    total_chunks = 0

    for email in emails:
        full_text = build_email_text(email)
        chunks = chunk_text(full_text)

        for chunk_index, chunk in enumerate(chunks):
            chunk_id = f"{email['message_id']}-{chunk_index}"

            cursor.execute(
                """
                INSERT INTO email_chunks (
                    chunk_id,
                    message_id,
                    thread_id,
                    subject,
                    from_email,
                    date,
                    chunk_index,
                    text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    email["message_id"],
                    email["thread_id"],
                    email["subject"],
                    email["from_email"],
                    email["date"],
                    chunk_index,
                    chunk,
                ),
            )

            total_chunks += 1

    connection.commit()
    connection.close()

    print(f"Emails processed: {len(emails)}")
    print(f"Chunks created: {total_chunks}")


if __name__ == "__main__":
    main()
