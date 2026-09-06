import unittest

from app.utils.emulator2.settings import (
    apply_changes,
    build_settings,
    detect_conflicts,
    read_saved,
    read_vbox_defaults,
    validate_changes,
)

#: 启动过但没在界面里动过设置的实例：28 键，没有 cpuCount / memorySize。
#:
#: **键名是平铺的、自带点号**，这是照实测的 ``leidianN.config`` 抄的。
#: 唯一的嵌套是 ``advancedSettings.resolution`` 的值。
#: 上一版这里写成了真嵌套对象，于是测试和实现一起错，谁也发现不了谁——
#: 写进去的配置雷电根本不认，但回读自洽，全绿。
CONFIG_28 = {
    "basicSettings.fps": 60,
    "basicSettings.name": "雷电模拟器",
    "basicSettings.autoRotate": True,
    "advancedSettings.resolution": {"width": 1280, "height": 720},
    "advancedSettings.resolutionDpi": 240,
}

#: 同一台实例的 .vbox：CPU 6 核 / 6144 MB **是雷电默认值**，不是用户设的。
VBOX_28 = """<?xml version="1.0"?>
<VirtualBox>
  <Machine uuid="{x}">
    <Hardware>
      <CPU count="6" hotplug="false"/>
      <Memory RAMSize="6144" PageFusion="false"/>
    </Hardware>
  </Machine>
</VirtualBox>
"""


class ReadSavedTest(unittest.TestCase):
    def test_only_keys_that_exist_come_back(self) -> None:
        saved = read_saved(CONFIG_28)

        self.assertEqual(saved, {"width": 1280, "height": 720, "dpi": 240, "fps": 60})

    def test_missing_config_is_empty_not_an_error(self) -> None:
        self.assertEqual(read_saved(None), {})
        self.assertEqual(read_saved({}), {})

    def test_float_that_is_a_whole_number_is_accepted(self) -> None:
        """雷电偶尔把内存写成 2048.0。"""
        saved = read_saved({"advancedSettings.memorySize": 2048.0})

        self.assertEqual(saved["memoryMb"], 2048)

    def test_bool_is_not_an_integer_here(self) -> None:
        """``bool`` 是 ``int`` 的子类，不挡掉的话 True 会变成 CPU 1 核。"""
        saved = read_saved({"advancedSettings.cpuCount": True})

        self.assertNotIn("cpu", saved)


class VboxDefaultsTest(unittest.TestCase):
    def test_reads_cpu_and_memory(self) -> None:
        self.assertEqual(read_vbox_defaults(VBOX_28), {"cpu": 6, "memoryMb": 6144})

    def test_absent_file_yields_nothing(self) -> None:
        self.assertEqual(read_vbox_defaults(None), {})


class FourStateTest(unittest.TestCase):
    """三层来源合成四态。混淆 saved 和 default 就是在骗用户。"""

    def test_config_keys_are_saved(self) -> None:
        settings = build_settings(CONFIG_28, VBOX_28)

        self.assertEqual(settings.fields["width"].state, "saved")
        self.assertEqual(settings.fields["width"].value, 1280)

    def test_vbox_fallback_is_marked_default_not_saved(self) -> None:
        """28 键实例的 6 核来自雷电默认，不能显示成用户保存过的设置。"""
        settings = build_settings(CONFIG_28, VBOX_28)

        self.assertEqual(settings.fields["cpu"].value, 6)
        self.assertEqual(settings.fields["cpu"].state, "default")
        self.assertEqual(settings.fields["memoryMb"].state, "default")

    def test_neither_source_has_it_is_unset(self) -> None:
        settings = build_settings({"basicSettings.fps": 60}, None)

        self.assertIsNone(settings.fields["cpu"].value)
        self.assertEqual(settings.fields["cpu"].state, "unset")

    def test_unreadable_config_is_its_own_state(self) -> None:
        """读不出文件和「没设过」是两回事，用户要做的事完全不同。"""
        settings = build_settings(None, None, readable=False)

        self.assertEqual(
            {item.state for item in settings.fields.values()}, {"unreadable"}
        )


class ValidateTest(unittest.TestCase):
    def test_accepts_a_normal_batch(self) -> None:
        cleaned = validate_changes({"width": 960, "height": 540, "cpu": 2})

        self.assertEqual(cleaned, {"width": 960, "height": 540, "cpu": 2})

    def test_empty_batch_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            validate_changes({})

    def test_unknown_field_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            validate_changes({"heightFrameRate": 1})

    def test_out_of_range_is_refused(self) -> None:
        for changes in ({"cpu": 0}, {"dpi": 5000}, {"memoryMb": 16}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    validate_changes(changes)

    def test_width_without_height_is_refused(self) -> None:
        """只写一半，模拟器会按另一半的旧值算，出来的分辨率不是用户要的。"""
        with self.assertRaises(ValueError):
            validate_changes({"width": 960})

    def test_non_integer_is_refused(self) -> None:
        for value in ("960", None, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_changes({"cpu": value})


class ConflictTest(unittest.TestCase):
    def test_untouched_field_changing_does_not_block_the_save(self) -> None:
        current = build_settings(CONFIG_28, VBOX_28)

        conflicts = detect_conflicts(current, {"fps": 30}, ["cpu"])

        self.assertEqual(conflicts, [])

    def test_field_being_written_changed_underneath_is_reported(self) -> None:
        current = build_settings(CONFIG_28, VBOX_28)

        conflicts = detect_conflicts(current, {"fps": 30}, ["fps"])

        self.assertEqual(conflicts, ["fps"])

    def test_no_baseline_means_no_comparison(self) -> None:
        """批量设置就是这么绕过冲突检查的——它本来就是明确的覆盖。"""
        current = build_settings(CONFIG_28, VBOX_28)

        self.assertEqual(detect_conflicts(current, {}, ["fps", "cpu"]), [])


class ApplyChangesTest(unittest.TestCase):
    def test_untouched_keys_survive(self) -> None:
        """28 键的实例保存后仍该是 28 键，不能被写成一份精简配置。"""
        merged = apply_changes(CONFIG_28, {"cpu": 2})

        self.assertEqual(merged["basicSettings.name"], "雷电模拟器")
        self.assertEqual(merged["advancedSettings.resolutionDpi"], 240)
        self.assertEqual(merged["advancedSettings.cpuCount"], 2)
        # 绝不能凭空造出一个雷电不认识的 advancedSettings 对象
        self.assertNotIn("advancedSettings", merged)

    def test_source_config_is_not_mutated(self) -> None:
        apply_changes(CONFIG_28, {"cpu": 2})

        self.assertNotIn("advancedSettings.cpuCount", CONFIG_28)

    def test_nested_resolution_is_created_when_absent(self) -> None:
        merged = apply_changes({}, {"width": 960, "height": 540})

        self.assertEqual(
            merged["advancedSettings.resolution"], {"width": 960, "height": 540}
        )

    def test_existing_resolution_siblings_survive(self) -> None:
        merged = apply_changes(CONFIG_28, {"width": 960, "height": 540})

        self.assertEqual(merged["advancedSettings.resolution"]["width"], 960)
        self.assertEqual(merged["advancedSettings.resolutionDpi"], 240)


if __name__ == "__main__":
    unittest.main()
