#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

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

#   Contact: DLmaster_361@163.com

"""
AUTO_MAA
AUTO_MAA安全服务
v4.4
作者：DLmaster_361
"""

import hashlib
import random
import secrets
import base64
import win32crypt
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Util.Padding import pad, unpad

from app.core import Config


class CryptoHandler:

    def get_PASSWORD(self, PASSWORD: str) -> None:
        """
        配置管理密钥

        :param PASSWORD: 管理密钥
        :type PASSWORD: str
        """

        # 生成目录
        Config.key_path.mkdir(parents=True, exist_ok=True)

        # 生成RSA密钥对
        key = RSA.generate(2048)
        public_key_local = key.publickey()
        private_key = key
        # 保存RSA公钥
        (Config.app_path / "data/key/public_key.pem").write_bytes(
            public_key_local.exportKey()
        )
        # 生成密钥转换与校验随机盐
        PASSWORD_salt = secrets.token_hex(random.randint(32, 1024))
        (Config.app_path / "data/key/PASSWORDsalt.txt").write_text(
            PASSWORD_salt,
            encoding="utf-8",
        )
        verify_salt = secrets.token_hex(random.randint(32, 1024))
        (Config.app_path / "data/key/verifysalt.txt").write_text(
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
        (Config.app_path / "data/key/AES_password_verify.bin").write_bytes(
            AES_password_verify
        )
        # AES-256加密RSA私钥并保存密文
        AES_key = AES.new(AES_password, AES.MODE_ECB)
        private_key_local = AES_key.encrypt(pad(private_key.exportKey(), 32))
        (Config.app_path / "data/key/private_key.bin").write_bytes(private_key_local)

    def AUTO_encryptor(self, note: str) -> str:
        """
        使用AUTO_MAA的算法加密数据

        :param note: 数据明文
        :type note: str
        """

        if note == "":
            return ""

        # 读取RSA公钥
        public_key_local = RSA.import_key(
            (Config.app_path / "data/key/public_key.pem").read_bytes()
        )
        # 使用RSA公钥对数据进行加密
        cipher = PKCS1_OAEP.new(public_key_local)
        encrypted = cipher.encrypt(note.encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")

    def AUTO_decryptor(self, note: str, PASSWORD: str) -> str:
        """
        使用AUTO_MAA的算法解密数据

        :param note: 数据密文
        :type note: str
        :param PASSWORD: 管理密钥
        :type PASSWORD: str
        :return: 解密后的明文
        :rtype: str
        """

        if note == "":
            return ""

        # 读入RSA私钥密文、盐与校验哈希值
        private_key_local = (
            (Config.app_path / "data/key/private_key.bin").read_bytes().strip()
        )
        PASSWORD_salt = (
            (Config.app_path / "data/key/PASSWORDsalt.txt")
            .read_text(encoding="utf-8")
            .strip()
        )
        verify_salt = (
            (Config.app_path / "data/key/verifysalt.txt")
            .read_text(encoding="utf-8")
            .strip()
        )
        AES_password_verify = (
            (Config.app_path / "data/key/AES_password_verify.bin").read_bytes().strip()
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
            note = decrypter.decrypt(base64.b64decode(note)).decode("utf-8")
            return note

    def change_PASSWORD(self, PASSWORD_old: str, PASSWORD_new: str) -> None:
        """
        修改管理密钥

        :param PASSWORD_old: 旧管理密钥
        :type PASSWORD_old: str
        :param PASSWORD_new: 新管理密钥
        :type PASSWORD_new: str
        """

        for script in Config.script_dict.values():

            # 使用旧管理密钥解密
            if script["Type"] == "Maa":
                for user in script["UserData"].values():
                    user["Password"] = self.AUTO_decryptor(
                        user["Config"].get(user["Config"].Info_Password), PASSWORD_old
                    )

        self.get_PASSWORD(PASSWORD_new)

        for script in Config.script_dict.values():

            # 使用新管理密钥重新加密
            if script["Type"] == "Maa":
                for user in script["UserData"].values():
                    user["Config"].set(
                        user["Config"].Info_Password,
                        self.AUTO_encryptor(user["Password"]),
                    )
                    user["Password"] = None
                    del user["Password"]

    def reset_PASSWORD(self, PASSWORD_new: str) -> None:
        """
        重置管理密钥

        :param PASSWORD_new: 新管理密钥
        :type PASSWORD_new: str
        """

        self.get_PASSWORD(PASSWORD_new)

        for script in Config.script_dict.values():

            if script["Type"] == "Maa":
                for user in script["UserData"].values():
                    user["Config"].set(
                        user["Config"].Info_Password, self.AUTO_encryptor("数据已重置")
                    )

    def win_encryptor(
        self, note: str, description: str = None, entropy: bytes = None
    ) -> str:
        """
        使用Windows DPAPI加密数据

        :param note: 数据明文
        :type note: str
        :param description: 描述信息
        :type description: str
        :param entropy: 随机熵
        :type entropy: bytes
        :return: 加密后的数据
        :rtype: str
        """

        if note == "":
            return ""

        encrypted = win32crypt.CryptProtectData(
            note.encode("utf-8"), description, entropy, None, None, 0
        )
        return base64.b64encode(encrypted).decode("utf-8")

    def win_decryptor(self, note: str, entropy: bytes = None) -> str:
        """
        使用Windows DPAPI解密数据

        :param note: 数据密文
        :type note: str
        :param entropy: 随机熵
        :type entropy: bytes
        :return: 解密后的明文
        :rtype: str
        """

        if note == "":
            return ""

        decrypted = win32crypt.CryptUnprotectData(
            base64.b64decode(note), entropy, None, None, 0
        )
        return decrypted[1].decode("utf-8")

    def check_PASSWORD(self, PASSWORD: str) -> bool:
        """
        验证管理密钥

        :param PASSWORD: 管理密钥
        :type PASSWORD: str
        :return: 是否验证通过
        :rtype: bool
        """

        return bool(
            self.AUTO_decryptor(self.AUTO_encryptor("-"), PASSWORD) != "管理密钥错误"
        )


Crypto = CryptoHandler()
