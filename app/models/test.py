import ConfigBase
from typing import Dict, Union, List
import uuid
from pathlib import Path


class TConfig(ConfigBase.ConfigBase):

    def __init__(self):
        super().__init__()

        self.Main_Name = ConfigBase.ConfigItem("Main", "Name", "Default Name")


class TestConfig(ConfigBase.ConfigBase):

    Main_Name = ConfigBase.ConfigItem("Main", "Name", "Default Name")
    Bool_Enabled = ConfigBase.ConfigItem(
        "Bool", "Enabled", False, ConfigBase.BoolValidator()
    )

    Mt = ConfigBase.MultipleConfig([TConfig])


root = Path.cwd()

test_config = TestConfig()

test_config.connect(root / "config.json")


test_config.set("Main", "Name", "New Name")
test_config.set("Bool", "Enabled", "qqq")


mt_test = ConfigBase.MultipleConfig([TestConfig])

mt_test.connect(root / "mt_config.json")


tc = mt_test.add(TestConfig)


for uid, config in mt_test.items():
    print(uid, config.toDict())
    config.set("Main", "Name", "Updated Name")

print(mt_test.toDict())

mt_test.add(TestConfig)
mt_test.setOrder(list(mt_test.keys())[::-1])

print(mt_test.toDict())


print("---------------------------------------------")

k: TestConfig = mt_test.add(TestConfig)
print(k.Mt.toDict())
