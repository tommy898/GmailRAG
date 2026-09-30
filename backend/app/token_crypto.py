from cryptography.fernet import Fernet, InvalidToken

from app.config import ConfigurationError, get_required_environment_variable


_fernet: Fernet | None = None


class TokenDecryptionError(Exception):
    pass


def get_token_cipher() -> Fernet:
    global _fernet

    if _fernet is None:
        encryption_key = get_required_environment_variable("TOKEN_ENCRYPTION_KEY")

        try:
            _fernet = Fernet(encryption_key.encode())
        except (TypeError, ValueError):
            raise ConfigurationError(
                "TOKEN_ENCRYPTION_KEY is invalid"
            ) from None

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
