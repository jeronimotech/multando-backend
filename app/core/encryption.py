"""Wallet key encryption utilities using envelope encryption.

Two-layer encryption:
1. DEK (Data Encryption Key): AES-256-GCM encrypts the private key
2. KEK (Key Encryption Key): AWS KMS (prod) or Fernet (dev) encrypts the DEK

Private keys are never stored in plaintext. They are only decrypted
in memory within Celery worker processes for transaction signing.
"""

import os
import secrets
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def generate_dek() -> bytes:
    """Generate a random 256-bit Data Encryption Key."""
    return secrets.token_bytes(32)


def encrypt_dek(dek: bytes) -> bytes:
    """Encrypt the DEK using the Key Encryption Key.

    In development: uses Fernet with WALLET_MASTER_KEY.
    In production: would use AWS KMS encrypt().

    Args:
        dek: The 256-bit data encryption key.

    Returns:
        Encrypted DEK bytes.
    """
    if settings.WALLET_ENCRYPTION_PROVIDER == "kms" and settings.AWS_KMS_KEY_ID:
        # Production: AWS KMS
        import boto3

        kms = boto3.client(
            "kms",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        response = kms.encrypt(
            KeyId=settings.AWS_KMS_KEY_ID,
            Plaintext=dek,
        )
        return response["CiphertextBlob"]

    # Development: Fernet-based local encryption
    from cryptography.fernet import Fernet

    master_key = settings.WALLET_MASTER_KEY
    if not master_key:
        master_key = Fernet.generate_key().decode()
    f = Fernet(master_key.encode() if isinstance(master_key, str) else master_key)
    return f.encrypt(dek)


def decrypt_dek(encrypted_dek: bytes) -> bytes:
    """Decrypt the DEK using the Key Encryption Key.

    Args:
        encrypted_dek: The encrypted data encryption key.

    Returns:
        Decrypted 256-bit DEK.
    """
    if settings.WALLET_ENCRYPTION_PROVIDER == "kms" and settings.AWS_KMS_KEY_ID:
        import boto3

        kms = boto3.client(
            "kms",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        response = kms.decrypt(CiphertextBlob=encrypted_dek)
        return response["Plaintext"]

    from cryptography.fernet import Fernet

    master_key = settings.WALLET_MASTER_KEY
    f = Fernet(master_key.encode() if isinstance(master_key, str) else master_key)
    return f.decrypt(encrypted_dek)


def encrypt_private_key(private_key: bytes, dek: bytes) -> Tuple[bytes, bytes]:
    """Encrypt a private key using AES-256-GCM.

    Args:
        private_key: The raw private key bytes (64 bytes for Solana).
        dek: The 256-bit data encryption key.

    Returns:
        Tuple of (ciphertext, iv/nonce).
    """
    iv = secrets.token_bytes(12)  # 96-bit nonce for GCM
    aesgcm = AESGCM(dek)
    ciphertext = aesgcm.encrypt(iv, private_key, None)
    return ciphertext, iv


def decrypt_private_key(ciphertext: bytes, dek: bytes, iv: bytes) -> bytes:
    """Decrypt a private key using AES-256-GCM.

    Args:
        ciphertext: The encrypted private key.
        dek: The 256-bit data encryption key.
        iv: The nonce used during encryption.

    Returns:
        The raw private key bytes.
    """
    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(iv, ciphertext, None)


def encrypt_wallet_key(private_key_bytes: bytes) -> Tuple[bytes, bytes, bytes]:
    """High-level: encrypt a wallet private key with envelope encryption.

    Args:
        private_key_bytes: The raw Solana private key (64 bytes).

    Returns:
        Tuple of (encrypted_private_key, encrypted_dek, iv).
    """
    dek = generate_dek()
    encrypted_pk, iv = encrypt_private_key(private_key_bytes, dek)
    encrypted_dek = encrypt_dek(dek)
    return encrypted_pk, encrypted_dek, iv


def decrypt_wallet_key(
    encrypted_private_key: bytes,
    encrypted_dek: bytes,
    iv: bytes,
) -> bytes:
    """High-level: decrypt a wallet private key from envelope encryption.

    Args:
        encrypted_private_key: The encrypted private key blob.
        encrypted_dek: The encrypted data encryption key.
        iv: The AES-GCM nonce.

    Returns:
        The raw Solana private key bytes (64 bytes).
    """
    dek = decrypt_dek(encrypted_dek)
    return decrypt_private_key(encrypted_private_key, dek, iv)
