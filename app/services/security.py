#   <AUTO_MAA:A MAA Multi Account Management and Automation Tool>
#   Copyright © <2024> <DLmaster361>

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   DLmaster_361@163.com

"""
AUTO_MAA
AUTO_MAA主程序
v4.2
作者：DLmaster_361
"""

import os
import hashlib
import random
import secrets
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Util.Padding import pad, unpad

from app import AppConfig


class CryptoHandler:

    def __init__(self, config: AppConfig):

        self.config = config

    def get_PASSWORD(self, PASSWORD: str) -> None:
        """配置管理密钥"""

        # 生成目录
        self.config.key_path.mkdir(parents=True, exist_ok=True)

        # 生成RSA密钥对
        key = RSA.generate(2048)
        public_key_local = key.publickey()
        private_key = key
        # 保存RSA公钥
        (self.config.app_path / "data/key/public_key.pem").write_bytes(
            public_key_local.exportKey()
        )
        # 生成密钥转换与校验随机盐
        PASSWORD_salt = secrets.token_hex(random.randint(32, 1024))
        (self.config.app_path / "data/key/PASSWORDsalt.txt").write_text(
            PASSWORD_salt,
            encoding="utf-8",
        )
        verify_salt = secrets.token_hex(random.randint(32, 1024))
        (self.config.app_path / "data/key/verifysalt.txt").write_text(
            verify_salt,
            encoding="utf-8",
        )
        # 将管理密钥转化为AES-256密钥
        AES_password = hashlib.sha256(
            (PASSWORD + PASSWORD_salt).encode("utf-8")
        ).digest()
        # 生成AES-256密钥校验哈希值并保存
        AES_password_verify = hashlib.sha256(
            AES_password + verify_salt.encode("utf-8")
        ).digest()
        (self.config.app_path / "data/key/AES_password_verify.bin").write_bytes(
            AES_password_verify
        )
        # AES-256加密RSA私钥并保存密文
        AES_key = AES.new(AES_password, AES.MODE_ECB)
        private_key_local = AES_key.encrypt(pad(private_key.exportKey(), 32))
        (self.config.app_path / "data/key/private_key.bin").write_bytes(
            private_key_local
        )

    def encryptx(self, note: str) -> bytes:
        """加密数据"""

        # 读取RSA公钥
        public_key_local = RSA.import_key(
            (self.config.app_path / "data/key/public_key.pem").read_bytes()
        )
        # 使用RSA公钥对数据进行加密
        cipher = PKCS1_OAEP.new(public_key_local)
        encrypted = cipher.encrypt(note.encode("utf-8"))
        return encrypted

    def decryptx(self, note: bytes, PASSWORD: str) -> str:
        """解密数据"""

        # 读入RSA私钥密文、盐与校验哈希值
        private_key_local = (
            (self.config.app_path / "data/key/private_key.bin").read_bytes().strip()
        )
        PASSWORD_salt = (
            (self.config.app_path / "data/key/PASSWORDsalt.txt")
            .read_text(encoding="utf-8")
            .strip()
        )
        verify_salt = (
            (self.config.app_path / "data/key/verifysalt.txt")
            .read_text(encoding="utf-8")
            .strip()
        )
        AES_password_verify = (
            (self.config.app_path / "data/key/AES_password_verify.bin")
            .read_bytes()
            .strip()
        )
        # 将管理密钥转化为AES-256密钥并验证
        AES_password = hashlib.sha256(
            (PASSWORD + PASSWORD_salt).encode("utf-8")
        ).digest()
        AES_password_SHA = hashlib.sha256(
            AES_password + verify_salt.encode("utf-8")
        ).digest()
        if AES_password_SHA != AES_password_verify:
            return "管理密钥错误"
        else:
            # AES解密RSA私钥
            AES_key = AES.new(AES_password, AES.MODE_ECB)
            private_key_pem = unpad(AES_key.decrypt(private_key_local), 32)
            private_key = RSA.import_key(private_key_pem)
            # 使用RSA私钥解密数据
            decrypter = PKCS1_OAEP.new(private_key)
            note = decrypter.decrypt(note)
            return note.decode("utf-8")

    def change_PASSWORD(self, data: list, PASSWORD_old: str, PASSWORD_new: str) -> None:
        """修改管理密钥"""

        # 使用旧管理密钥解密
        new_data = []
        for i in range(len(data)):
            new_data.append(self.decryptx(data[i][12], PASSWORD_old))
        # 使用新管理密钥重新加密
        self.get_PASSWORD(PASSWORD_new)
        for i in range(len(data)):
            self.config.cur.execute(
                "UPDATE adminx SET password = ? WHERE mode = ? AND uid = ?",
                (
                    self.encryptx(new_data[i]),
                    data[i][15],
                    data[i][16],
                ),
            )
            self.config.db.commit(),
            new_data[i] = None
        del new_data

    def check_PASSWORD(self, PASSWORD: str) -> bool:
        """验证管理密钥"""

        return bool(self.decryptx(self.encryptx(""), PASSWORD) != "管理密钥错误")
