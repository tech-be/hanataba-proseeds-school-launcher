"""パスワードの移行（旧 3DES 復号 → bcrypt 再ハッシュ）。

lw2 は**復号できる形**でパスワードを保持している（`library/Crypt.class.php`）。

```
base64( 3DES-CBC( 平文 ) )      鍵 = substr(md5(秘密鍵), 0, 24)
                                IV  = substr(md5(鍵), 0, 8)      ゼロ埋め
```

新環境は bcrypt（`libs/auth/password.go` / `bcrypt.DefaultCost` = 10）。
**会員にパスワードの再設定を求めない**という決定のため、移行時に一度だけ
平文を経由して bcrypt に入れ替える。

**扱いの決まり**

- 秘密鍵は**環境変数から**受け取る（設定ファイルに書かない）
- 平文は**ログにも例外にも出さない。** 件数と会員 ID だけを扱う
- 復号できなかったものは**空のまま入れない。** 件数を出して判断に上げる
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field

from ..errors import ConfigError

#: 旧環境の秘密鍵を渡す環境変数（`application.ini` の `security.mcrypt.key`）
SECRET_ENV = "LW2_CRYPT_KEY"

#: 新環境と同じ bcrypt のコスト（`bcrypt.DefaultCost`）
DEFAULT_COST = 10


class LegacyPasswordCipher:
    """lw2 の `Crypt` と**同じ鍵導出・同じ方式**で復号する。

    鍵導出を1文字でも変えると、全件が復号できないのではなく
    **一部だけ意味のない文字列になる**ので、ここは lw2 の実装をそのまま写す。
    """

    BLOCK_SIZE = 8

    def __init__(self, secret: str) -> None:
        if not secret:
            raise ConfigError(
                f"旧環境の秘密鍵が無い。環境変数 {SECRET_ENV} に "
                "lw2 の `security.mcrypt.key` を入れる"
            )
        self._key = hashlib.md5(secret.encode()).hexdigest()[:24].encode()
        self._iv = hashlib.md5(self._key).hexdigest()[: self.BLOCK_SIZE].encode()

    def decrypt(self, stored: str | bytes | None) -> str | None:
        """`base64(3DES(平文))` を平文に戻す。**戻せないときは `None`。**"""
        if stored is None:
            return None
        text = stored.decode("ascii", "ignore") if isinstance(stored, bytes) else str(stored)
        text = text.strip()
        if not text:
            return None
        try:
            raw = base64.b64decode(text, validate=True)
        except Exception:
            return None
        if not raw or len(raw) % self.BLOCK_SIZE:
            return None
        try:
            from Crypto.Cipher import DES3
        except ModuleNotFoundError as exc:  # pragma: no cover - 環境依存
            raise ConfigError("pycryptodome が要る: pip install -r requirements.txt") from exc
        plain = DES3.new(self._key, DES3.MODE_CBC, self._iv).decrypt(raw)
        plain = plain.rstrip(b"\x00")  # mcrypt のゼロ埋め
        try:
            return plain.decode("utf-8")
        except UnicodeDecodeError:
            return None


def rehash(plaintext: str, cost: int = DEFAULT_COST) -> str:
    """平文を bcrypt にする。**新環境が作るのと同じ `$2a$` 形式。**"""
    try:
        import bcrypt
    except ModuleNotFoundError as exc:  # pragma: no cover - 環境依存
        raise ConfigError("bcrypt が要る: pip install -r requirements.txt") from exc
    # 新環境（Go の golang.org/x/crypto/bcrypt）は `$2a$` を作る。
    # bcrypt は72バイトを超える分を黙って捨てるので、超過は呼び出し側で弾く
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(cost, prefix=b"2a")).decode()


#: bcrypt が黙って切り捨てる長さ（`libs/auth/password.go` の `PasswordMaxBytes`）
MAX_BYTES = 72


@dataclass
class PasswordMigration:
    """会員ごとの結果を数える。**平文は持たない。**"""

    cipher: LegacyPasswordCipher
    cost: int = DEFAULT_COST
    migrated: int = 0
    #: 復号できなかった会員の旧 ID（鍵違い・壊れた値）
    undecryptable: list[int] = field(default_factory=list)
    #: 旧の値が空だった会員の旧 ID
    empty: list[int] = field(default_factory=list)
    #: bcrypt の 72 バイト制限を超える会員の旧 ID
    too_long: list[int] = field(default_factory=list)

    def hash_for(self, stored: object, user_id: int) -> str | None:
        """1件分の `password_hash`。**入れられないときは `None` を返す。**"""
        plaintext = self.cipher.decrypt(stored)
        if plaintext is None:
            if stored is None or not str(stored).strip():
                self.empty.append(user_id)
            else:
                self.undecryptable.append(user_id)
            return None
        if len(plaintext.encode("utf-8")) > MAX_BYTES:
            self.too_long.append(user_id)
            return None
        self.migrated += 1
        return rehash(plaintext, self.cost)

    def summary(self) -> str:
        parts = [f"再ハッシュ {self.migrated} 件"]
        if self.empty:
            parts.append(f"旧が空 {len(self.empty)} 件")
        if self.undecryptable:
            parts.append(f"復号できず {len(self.undecryptable)} 件（例: {self.undecryptable[:5]}）")
        if self.too_long:
            parts.append(f"72バイト超 {len(self.too_long)} 件（例: {self.too_long[:5]}）")
        return " / ".join(parts)

    @property
    def unusable(self) -> list[int]:
        """**ログインできない状態で入る会員。** 0 件でなければ判断に上げる。"""
        return sorted(self.empty + self.undecryptable + self.too_long)
