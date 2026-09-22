"""パスワード移行のテスト。

**平文は扱うが、テストの中で作ったものだけ。** 実データは使わない。
"""

from __future__ import annotations

import base64
import hashlib
import unittest

import bcrypt
from Crypto.Cipher import DES3

from migrator.core.passwords import LegacyPasswordCipher, PasswordMigration, rehash
from migrator.errors import ConfigError

SECRET = "test-secret-key"


def php_encrypt(plaintext: str, secret: str = SECRET) -> str:
    """lw2 の `Crypt::encrypt` と同じことをする（テスト用の逆方向）。"""
    key = hashlib.md5(secret.encode()).hexdigest()[:24].encode()
    iv = hashlib.md5(key).hexdigest()[:8].encode()
    data = plaintext.encode("utf-8")
    data += b"\x00" * (-len(data) % 8)  # mcrypt のゼロ埋め
    return base64.b64encode(DES3.new(key, DES3.MODE_CBC, iv).encrypt(data)).decode()


class CipherTest(unittest.TestCase):
    def test_round_trip(self):
        cipher = LegacyPasswordCipher(SECRET)
        for plaintext in ("abc123", "password", "8文字ちょうど", "a" * 64):
            self.assertEqual(cipher.decrypt(php_encrypt(plaintext)), plaintext)

    def test_key_derivation_is_pinned(self):
        """**鍵導出を変えると全件が壊れる**ので、値そのものを固定する。"""
        cipher = LegacyPasswordCipher(SECRET)
        expected_key = hashlib.md5(SECRET.encode()).hexdigest()[:24].encode()
        self.assertEqual(cipher._key, expected_key)
        self.assertEqual(cipher._iv, hashlib.md5(expected_key).hexdigest()[:8].encode())

    def test_unusable_values_return_none(self):
        cipher = LegacyPasswordCipher(SECRET)
        for value in (None, "", "   ", "not-base64!!", base64.b64encode(b"12345").decode()):
            self.assertIsNone(cipher.decrypt(value))

    def test_wrong_key_does_not_raise(self):
        """鍵が違っても例外にせず `None`。**件数として上がることが大事。**"""
        other = LegacyPasswordCipher("another-secret")
        result = other.decrypt(php_encrypt("abc123"))
        self.assertNotEqual(result, "abc123")

    def test_empty_secret_stops(self):
        with self.assertRaises(ConfigError):
            LegacyPasswordCipher("")


class RehashTest(unittest.TestCase):
    def test_new_environment_can_verify(self):
        """新環境（Go の bcrypt）が作るのと同じ `$2a$` 形式にする。"""
        hashed = rehash("abc123", cost=4)
        self.assertTrue(hashed.startswith("$2a$"))
        self.assertTrue(bcrypt.checkpw(b"abc123", hashed.encode()))


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.migration = PasswordMigration(LegacyPasswordCipher(SECRET), cost=4)

    def test_counts_by_reason(self):
        self.assertIsNotNone(self.migration.hash_for(php_encrypt("abc123"), 1))
        self.assertIsNone(self.migration.hash_for("", 2))
        self.assertIsNone(self.migration.hash_for("not-base64!!", 3))
        self.assertIsNone(self.migration.hash_for(php_encrypt("a" * 73), 4))
        self.assertEqual(self.migration.migrated, 1)
        self.assertEqual(self.migration.empty, [2])
        self.assertEqual(self.migration.undecryptable, [3])
        self.assertEqual(self.migration.too_long, [4])
        self.assertEqual(self.migration.unusable, [2, 3, 4])

    def test_summary_has_no_plaintext(self):
        self.migration.hash_for(php_encrypt("secret-password"), 1)
        self.assertNotIn("secret-password", self.migration.summary())
