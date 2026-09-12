# v5.4.0 结构下需先初始化 app.core：直接先导 app.task 会经
# MAA.__init__ -> manager -> app.core.__init__ -> task_manager 触发循环导入
# （dev 侧已重构消除，此处为 release 局部守卫，不影响生产入口）。
import app.core  # noqa: F401

from app.task.MAA.AutoProxy import _has_completed_annihilation_week


def test_week_completed_when_annihilation_done_before_proxy() -> None:
    # MAA 未进到副本门口（无理智识别行），完成即周内剿灭在代理前已完成
    assert (
        _has_completed_annihilation_week("开始任务: 剿灭作战\n完成任务: 剿灭作战")
        is True
    )


def test_week_completed_when_progress_reaches_cap() -> None:
    assert (
        _has_completed_annihilation_week(
            "理智: 106/205\n完成任务: 剿灭作战\n剿灭模式 : 1800 / 1800"
        )
        is True
    )
    assert (
        _has_completed_annihilation_week(
            "理智: 5/210\n剿灭模式 : 1850 / 1800\n完成任务: 剿灭作战"
        )
        is True
    )


def test_week_not_completed_without_cap_progress() -> None:
    # 开战了但理智不足没能打满进度
    assert (
        _has_completed_annihilation_week(
            "理智: 5/210\n完成任务: 剿灭作战\n剿灭模式 : 1480 / 1800"
        )
        is False
    )
    # 进到副本门口却因理智不足没有开战
    assert (
        _has_completed_annihilation_week(
            "理智: 24/210\n开始任务: 剿灭作战\n完成任务: 剿灭作战"
        )
        is False
    )
    # 没有完成行不参与判定
    assert _has_completed_annihilation_week("剿灭模式 : 1480 / 1800") is False
