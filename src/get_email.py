import sqlite3

connection = sqlite3.connect('data/gmailrag.sqlite3')
connection.row_factory = sqlite3.Row
cursor = connection.cursor()

cursor.execute('SELECT * FROM emails')

rows = cursor.fetchall()

for row in rows:
    print("Message ID:", row["message_id"])
    print("Thread ID:", row["thread_id"])
    print("From:", row["from_email"])
    print("To:", row["to_email"])
    print("Subject:", row["subject"])
    print("Date:", row["date"])
    print("Snippet:", row["snippet"])
    print("Body:", row["body"])
    print("-" * 80)

connection.close()