"""Stupid tests that ensure logging works as expected"""

import logging as log
import sys
import threading
from io import StringIO

import beets.logging as blog
import beetsplug
from beets import plugins, ui
from beets.test import _common, helper
from beets.test.helper import (
    AsIsImporterMixin,
    BeetsTestCase,
    ImportTestCase,
    PluginMixin,
)


class LoggingTest(BeetsTestCase):
    def test_logging_management(self):
        l1 = log.getLogger("foo123")
        l2 = blog.getLogger("foo123")
        assert l1 == l2
        assert l1.__class__ == log.Logger

        l3 = blog.getLogger("bar123")
        l4 = log.getLogger("bar123")
        assert l3 == l4
        assert l3.__class__ == blog.BeetsLogger
        assert isinstance(
            l3, (blog.StrFormatLogger, blog.ThreadLocalLevelLogger)
        )

        l5 = l3.getChild("shalala")
        assert l5.__class__ == blog.BeetsLogger

        l6 = blog.getLogger()
        assert l1 != l6

    def test_str_format_logging(self):
        logger = blog.getLogger("baz123")
        stream = StringIO()
        handler = log.StreamHandler(stream)

        logger.addHandler(handler)
        logger.propagate = False

        logger.warning("foo {0} {bar}", "oof", bar="baz")
        handler.flush()
        assert stream.getvalue(), "foo oof baz"


class LoggingLevelTest(AsIsImporterMixin, PluginMixin, ImportTestCase):
    plugin = "dummy"

    class DummyModule:
        class DummyPlugin(plugins.BeetsPlugin):
            def __init__(self):
                plugins.BeetsPlugin.__init__(self, "dummy")
                self.import_stages = [self.import_stage]
                self.register_listener("dummy_event", self.listener)

            def log_all(self, name):
                self._log.debug("debug " + name)
                self._log.info("info " + name)
                self._log.warning("warning " + name)

            def commands(self):
                cmd = ui.Subcommand("dummy")
                cmd.func = lambda _, __, ___: self.log_all("cmd")
                return (cmd,)

            def import_stage(self, session, task):
                self.log_all("import_stage")

            def listener(self):
                self.log_all("listener")

    def setUp(self):
        sys.modules["beetsplug.dummy"] = self.DummyModule
        beetsplug.dummy = self.DummyModule
        super().setUp()

    def test_command_level0(self):
        self.config["verbose"] = 0
        with helper.capture_log() as logs:
            self.run_command("dummy")
        assert "dummy: warning cmd" in logs
        assert "dummy: info cmd" in logs
        assert "dummy: debug cmd" not in logs

    def test_command_level1(self):
        self.config["verbose"] = 1
        with helper.capture_log() as logs:
            self.run_command("dummy")
        assert "dummy: warning cmd" in logs
        assert "dummy: info cmd" in logs
        assert "dummy: debug cmd" in logs

    def test_command_level2(self):
        self.config["verbose"] = 2
        with helper.capture_log() as logs:
            self.run_command("dummy")
        assert "dummy: warning cmd" in logs
        assert "dummy: info cmd" in logs
        assert "dummy: debug cmd" in logs

    def test_listener_level0(self):
        self.config["verbose"] = 0
        with helper.capture_log() as logs:
            plugins.send("dummy_event")
        assert "dummy: warning listener" in logs
        assert "dummy: info listener" not in logs
        assert "dummy: debug listener" not in logs

    def test_listener_level1(self):
        self.config["verbose"] = 1
        with helper.capture_log() as logs:
            plugins.send("dummy_event")
        assert "dummy: warning listener" in logs
        assert "dummy: info listener" in logs
        assert "dummy: debug listener" not in logs

    def test_listener_level2(self):
        self.config["verbose"] = 2
        with helper.capture_log() as logs:
            plugins.send("dummy_event")
        assert "dummy: warning listener" in logs
        assert "dummy: info listener" in logs
        assert "dummy: debug listener" in logs

    def test_import_stage_level0(self):
        self.config["verbose"] = 0
        with helper.capture_log() as logs:
            self.run_asis_importer()
        assert "dummy: warning import_stage" in logs
        assert "dummy: info import_stage" not in logs
        assert "dummy: debug import_stage" not in logs

    def test_import_stage_level1(self):
        self.config["verbose"] = 1
        with helper.capture_log() as logs:
            self.run_asis_importer()
        assert "dummy: warning import_stage" in logs
        assert "dummy: info import_stage" in logs
        assert "dummy: debug import_stage" not in logs

    def test_import_stage_level2(self):
        self.config["verbose"] = 2
        with helper.capture_log() as logs:
            self.run_asis_importer()
        assert "dummy: warning import_stage" in logs
        assert "dummy: info import_stage" in logs
        assert "dummy: debug import_stage" in logs


@_common.slow_test()
class ConcurrentEventsTest(AsIsImporterMixin, ImportTestCase):
    """Similar to LoggingLevelTest but lower-level and focused on multiple
    events interaction. Since this is a bit heavy we don't do it in
    LoggingLevelTest.
    """

    db_on_disk = True

    class DummyPlugin(plugins.BeetsPlugin):
        def __init__(self, test_case):
            plugins.BeetsPlugin.__init__(self, "dummy")
            self.register_listener("dummy_event1", self.listener1)
            self.register_listener("dummy_event2", self.listener2)
            self.lock1 = threading.Lock()
            self.lock2 = threading.Lock()
            self.test_case = test_case
            self.exc = None
            self.t1_step = self.t2_step = 0

        def log_all(self, name):
            self._log.debug("debug " + name)
            self._log.info("info " + name)
            self._log.warning("warning " + name)

        def listener1(self):
            try:
                assert self._log.level == log.INFO
                self.t1_step = 1
                self.lock1.acquire()
                assert self._log.level == log.INFO
                self.t1_step = 2
            except Exception as e:
                self.exc = e

        def listener2(self):
            try:
                assert self._log.level == log.DEBUG
                self.t2_step = 1
                self.lock2.acquire()
                assert self._log.level == log.DEBUG
                self.t2_step = 2
            except Exception as e:
                self.exc = e

    def test_concurrent_events(self):
        dp = self.DummyPlugin(self)

        def check_dp_exc():
            if dp.exc:
                raise dp.exc

        try:
            dp.lock1.acquire()
            dp.lock2.acquire()
            assert dp._log.level == log.NOTSET

            self.config["verbose"] = 1
            t1 = threading.Thread(target=dp.listeners["dummy_event1"][0])
            t1.start()  # blocked. t1 tested its log level
            while dp.t1_step != 1:
                check_dp_exc()
            assert t1.is_alive()
            assert dp._log.level == log.NOTSET

            self.config["verbose"] = 2
            t2 = threading.Thread(target=dp.listeners["dummy_event2"][0])
            t2.start()  # blocked. t2 tested its log level
            while dp.t2_step != 1:
                check_dp_exc()
            assert t2.is_alive()
            assert dp._log.level == log.NOTSET

            dp.lock1.release()  # dummy_event1 tests its log level + finishes
            while dp.t1_step != 2:
                check_dp_exc()
            t1.join(0.1)
            assert not t1.is_alive()
            assert t2.is_alive()
            assert dp._log.level == log.NOTSET

            dp.lock2.release()  # dummy_event2 tests its log level + finishes
            while dp.t2_step != 2:
                check_dp_exc()
            t2.join(0.1)
            assert not t2.is_alive()

        except Exception:
            print("Alive threads:", threading.enumerate())
            if dp.lock1.locked():
                print("Releasing lock1 after exception in test")
                dp.lock1.release()
            if dp.lock2.locked():
                print("Releasing lock2 after exception in test")
                dp.lock2.release()
            print("Alive threads:", threading.enumerate())
            raise

    def test_root_logger_levels(self):
        """Root logger level should be shared between threads."""
        self.config["threaded"] = True

        blog.getLogger("beets").set_global_level(blog.WARNING)
        with helper.capture_log() as logs:
            self.run_asis_importer()
        assert logs == []

        blog.getLogger("beets").set_global_level(blog.INFO)
        with helper.capture_log() as logs:
            self.run_asis_importer()
        for line in logs:
            assert "import" in line
            assert "album" in line

        blog.getLogger("beets").set_global_level(blog.DEBUG)
        with helper.capture_log() as logs:
            self.run_asis_importer()
        assert "Sending event: database_change" in logs
