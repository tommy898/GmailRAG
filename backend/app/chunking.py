from collections.abc import Mapping


CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
CHUNKER_VERSION = f"char-{CHUNK_SIZE}-overlap-{CHUNK_OVERLAP}-v1"


def safe_text(value: object) -> str:
    if value is None:
        return ""

    return str(value).strip()


def build_email_text(email: Mapping[str, object]) -> str:
    subject = safe_text(email.get("subject"))
    from_email = safe_text(email.get("from_email"))
    date = safe_text(email.get("gmail_date_raw") or email.get("sent_at"))
    body = safe_text(email.get("body_text"))

    parts = [
        f"Subject: {subject}",
        f"From: {from_email}",
        f"Date: {date}",
        "",
        body,
    ]

    return "\n".join(parts).strip()


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    clean_text = text.strip()

    if not clean_text:
        return []

    if len(clean_text) <= chunk_size:
        return [clean_text]

    chunks = []
    start = 0

    while start < len(clean_text):
        end = start + chunk_size
        chunk = clean_text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(clean_text):
            break

        start = end - overlap

    return chunks


def chunk_email(email: Mapping[str, object]) -> list[str]:
    return chunk_text(build_email_text(email))
