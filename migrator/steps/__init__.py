"""1テーブル（または1つの論理単位）= 1 Step。

Step は **extract → transform → load** の3メソッドだけを持ち、
変換は core/ の部品を呼ぶ。Step 同士は `depends_on` でしか関係しない。
"""
