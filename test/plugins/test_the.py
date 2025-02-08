"""Tests for the 'the' plugin"""

from beets import config
from beets.test.helper import BeetsTestCase
from beetsplug.the import FORMAT, PATTERN_A, PATTERN_THE, ThePlugin


class ThePluginTest(BeetsTestCase):
    def test_unthe_with_default_patterns(self):
        assert ThePlugin().unthe("", PATTERN_THE) == ""
        assert (
            ThePlugin().unthe("The Something", PATTERN_THE) == "Something, The"
        )
        assert ThePlugin().unthe("The The", PATTERN_THE) == "The, The"
        assert ThePlugin().unthe("The    The", PATTERN_THE) == "The, The"
        assert ThePlugin().unthe("The   The   X", PATTERN_THE) == "The   X, The"
        assert ThePlugin().unthe("the The", PATTERN_THE) == "The, the"
        assert (
            ThePlugin().unthe("Protected The", PATTERN_THE) == "Protected The"
        )
        assert ThePlugin().unthe("A Boy", PATTERN_A) == "Boy, A"
        assert ThePlugin().unthe("a girl", PATTERN_A) == "girl, a"
        assert ThePlugin().unthe("An Apple", PATTERN_A) == "Apple, An"
        assert ThePlugin().unthe("An A Thing", PATTERN_A) == "A Thing, An"
        assert ThePlugin().unthe("the An Arse", PATTERN_A) == "the An Arse"
        assert (
            ThePlugin().unthe("TET - Travailleur", PATTERN_THE)
            == "TET - Travailleur"
        )

    def test_unthe_with_strip(self):
        config["the"]["strip"] = True
        assert ThePlugin().unthe("The Something", PATTERN_THE) == "Something"
        assert ThePlugin().unthe("An A", PATTERN_A) == "A"

    def test_template_function_with_defaults(self):
        ThePlugin().patterns = [PATTERN_THE, PATTERN_A]
        assert ThePlugin().the_template_func("The The") == "The, The"
        assert ThePlugin().the_template_func("An A") == "A, An"

    def test_custom_pattern(self):
        config["the"]["patterns"] = ["^test\\s"]
        config["the"]["format"] = FORMAT
        assert ThePlugin().the_template_func("test passed") == "passed, test"

    def test_custom_format(self):
        config["the"]["patterns"] = [PATTERN_THE, PATTERN_A]
        config["the"]["format"] = "{1} ({0})"
        assert ThePlugin().the_template_func("The A") == "The (A)"
