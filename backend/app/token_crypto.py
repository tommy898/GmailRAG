import os

from cryptography.fernet import Fernet, InvalidToken


_fernet: Fernet | None = None


class TokenDecryptionError(Exception):
    pass


def get_token_cipher() -> Fernet:
    global _fernet

    if _fernet is None:
        encryption_key = os.environ.get("TOKEN_ENCRYPTION_KEY")

        if not encryption_key:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY environment variable is not set"
            )

        try:
            _fernet = Fernet(encryption_key.encode())
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY is invalid"
            ) from exc

    return _fernet


def encrypt_token(token: str) -> str:
    if not token:
        raise ValueError("Token cannot be empty")

    encrypted = get_token_cipher().encrypt(token.encode())
    return encrypted.decode()


def decrypt_token(encrypted_token: str) -> str:
    if not encrypted_token:
        raise ValueError("Encrypted token cannot be empty")

    try:
        decrypted = get_token_cipher().decrypt(
            encrypted_token.encode()
        )
    except InvalidToken as exc:
        raise TokenDecryptionError(
            "Stored token could not be decrypted"
        ) from exc

    return decrypted.decode()