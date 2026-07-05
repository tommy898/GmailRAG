import sqlite3

connection = sqlite3.connect('data/gmailrag.sqlite3')
cursor = connection.cursor()

cursor.execute(
    """
    INSERT INTO emails(
    message_id,
    thread_id,
    from_email,
    to_email,
    subject,
    date,
    snippet,
    body
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        "fake-message-2",
        "fake-thread-2",
        "bob@example.com",
        "tommy@example.com",
        "Second test email",
        "2026-07-04",
        "This is another fake preview.",
        "This is another fake email body.",
    ),
)
connection.commit()
connection.close()