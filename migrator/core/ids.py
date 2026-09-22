"""ID の採番（docs/migration-spec.md 3.2）。

新環境の ID は `char(26)` の ULID。26文字の Crockford Base32 で、
先頭10文字がミリ秒精度の生成時刻(48bit)、残り16文字がランダム部(80bit)。

移行では毎回ランダムに振らず **決定論 ULID** を使う。旧テーブル名 + 旧主キーから
同じ値を再現できるため、途中で失敗して流し直しても二重登録にならない。

**テナントだけは例外。** `tenants.id` はフェーズ1で採番した1値を設定値として配り、
どこでも再計算しない（採番が散ると別テナントの ID が生まれ、データが2つに割れる）。
"""

from __future__ import annotations

import hashlib
import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


def encode_ulid(timestamp_ms: int, randomness: bytes) -> str:
    """時刻(ms)と80bitのランダム部から ULID 文字列を組み立てる。"""
    if not 0 <= timestamp_ms < (1 << 48):
        raise ValueError(f"ULID の時刻部が範囲外: {timestamp_ms}")
    if len(randomness) != 10:
        raise ValueError("ULID のランダム部は 80bit (10 バイト)")
    return _encode(timestamp_ms, 10) + _encode(int.from_bytes(randomness, "big"), 16)


def random_ulid(now_ms: int | None = None) -> str:
    """ランダムな ULID。**移行では原則使わない**（再実行で値が変わるため）。"""
    return encode_ulid(now_ms if now_ms is not None else int(time.time() * 1000), os.urandom(10))


class UlidFactory:
    """決定論 ULID の採番器。

    同じ `(namespace, table, key)` からは常に同じ ULID を返す。

    - **時刻部**: 旧レコードの作成日時があればそれを使う。無ければ `epoch_ms`
      （移行の基準時刻）。ULID の辞書順が旧データの時系列と揃う
    - **ランダム部**: 名前空間・テーブル名・旧主キーの SHA-256 の先頭80bit

    `namespace` は移行の世代を表す。**採番規則を変えたら namespace も変える**
    （変えずに変更すると、前回の実行と ID が食い違って二重登録になる）。
    """

    def __init__(self, namespace: str, epoch_ms: int) -> None:
        if not namespace:
            raise ValueError("namespace は必須")
        self._namespace = namespace
        self._epoch_ms = epoch_ms

    @property
    def namespace(self) -> str:
        return self._namespace

    def for_row(self, table: str, key: object, created_at_ms: int | None = None) -> str:
        """旧テーブルの1行に対する ULID を返す。"""
        if key is None:
            raise ValueError(f"{table}: 旧主キーが None では採番できない")
        digest = hashlib.sha256(f"{self._namespace}:{table}:{key}".encode()).digest()
        return encode_ulid(created_at_ms if created_at_ms is not None else self._epoch_ms, digest[:10])


class TenantId:
    """テナントの ULID を1か所に閉じるための入れ物。

    フェーズ1が `resolve()` で確定させ、以降の Step は `value` を読むだけ。
    **Step が自分で採番することを禁じる**（テナントが二重にできる）。
    """

    def __init__(self) -> None:
        self._value: str | None = None

    @property
    def value(self) -> str:
        if self._value is None:
            raise RuntimeError("tenants の行を作る前に tenant_id を参照した（フェーズ1が先）")
        return self._value

    @property
    def resolved(self) -> bool:
        return self._value is not None

    def resolve(self, value: str) -> str:
        if len(value) != 26:
            raise ValueError(f"tenant_id は26文字の ULID: {value!r}")
        if self._value is not None and self._value != value:
            raise RuntimeError(f"tenant_id を二重に採番した: {self._value} と {value}")
        self._value = value
        return value
