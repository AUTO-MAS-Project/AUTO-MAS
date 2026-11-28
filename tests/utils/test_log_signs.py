from app.utils.common.log import patterns


def test_ordered_signs_report_the_winning_rule_even_for_an_empty_match():
    rules = {
        "failure": patterns.compile_log_signs(r"error \d+", "Regex"),
        "success": patterns.compile_log_signs(r"(?=finished)", "Regex"),
    }
    assert patterns.match_log_signs("finished: error 42", rules) == (
        "failure",
        "error 42",
    )
    assert patterns.match_log_signs("finished", rules) == ("success", "")
    assert patterns.match_log_signs("running", rules) is None
