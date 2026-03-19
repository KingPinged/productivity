import pytest
from unittest.mock import patch, MagicMock

from src.planner.encryption import EncryptionManager


@pytest.fixture
def manager():
    with patch("src.planner.encryption.keyring") as mock_keyring:
        mock_keyring.get_password.return_value = None
        mgr = EncryptionManager(service_name="test-planner")
        yield mgr


class TestEncryptionManager:
    def test_encrypt_decrypt_roundtrip(self, manager):
        plaintext = "my-secret-token-12345"
        encrypted = manager.encrypt(plaintext)
        assert encrypted != plaintext
        decrypted = manager.decrypt(encrypted)
        assert decrypted == plaintext

    def test_encrypt_produces_different_output_each_call(self, manager):
        plaintext = "same-input"
        a = manager.encrypt(plaintext)
        b = manager.encrypt(plaintext)
        assert a != b

    def test_decrypt_invalid_data_raises(self, manager):
        with pytest.raises(Exception):
            manager.decrypt("not-valid-fernet-data")

    def test_key_is_stored_in_keyring(self):
        with patch("src.planner.encryption.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None
            EncryptionManager(service_name="test-planner")
            mock_keyring.set_password.assert_called_once()
            call_args = mock_keyring.set_password.call_args
            assert call_args[0][0] == "test-planner"
            assert call_args[0][1] == "fernet-key"

    def test_existing_key_is_reused(self):
        from cryptography.fernet import Fernet

        existing_key = Fernet.generate_key().decode()
        with patch("src.planner.encryption.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = existing_key
            mgr = EncryptionManager(service_name="test-planner")
            mock_keyring.set_password.assert_not_called()
            encrypted = mgr.encrypt("test")
            assert mgr.decrypt(encrypted) == "test"
