import keyring
from cryptography.fernet import Fernet


class EncryptionManager:
    def __init__(self, service_name: str = "productivity-planner"):
        self._service_name = service_name
        self._fernet = Fernet(self._get_or_create_key())

    def _get_or_create_key(self) -> bytes:
        stored_key = keyring.get_password(self._service_name, "fernet-key")
        if stored_key:
            return stored_key.encode()
        new_key = Fernet.generate_key()
        keyring.set_password(self._service_name, "fernet-key", new_key.decode())
        return new_key

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
