"""Meta WhatsApp Flows endpoint encryption (data-exchange).

Meta sends {encrypted_flow_data, encrypted_aes_key, initial_vector} (all base64). The AES key
is RSA-OAEP(SHA-256) encrypted with the business public key; the flow data is AES-128-GCM
encrypted with that key + IV (ciphertext has the 16-byte tag appended). The response is
AES-GCM encrypted with the same key and the bitwise-inverted IV, returned base64 as the body.
"""

from __future__ import annotations

import json
from base64 import b64decode, b64encode

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def decrypt_request(body: dict, private_key_pem: str, passphrase: str | None = None):
    enc_aes_key = b64decode(body["encrypted_aes_key"])
    enc_flow_data = b64decode(body["encrypted_flow_data"])
    iv = b64decode(body["initial_vector"])

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(),
        password=passphrase.encode() if passphrase else None,
    )
    aes_key = private_key.decrypt(
        enc_aes_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    plaintext = AESGCM(aes_key).decrypt(iv, enc_flow_data, None)
    return json.loads(plaintext.decode("utf-8")), aes_key, iv


def encrypt_response(response: dict, aes_key: bytes, iv: bytes) -> str:
    flipped_iv = bytes(b ^ 0xFF for b in iv)
    ct = AESGCM(aes_key).encrypt(flipped_iv, json.dumps(response).encode("utf-8"), None)
    return b64encode(ct).decode("utf-8")
