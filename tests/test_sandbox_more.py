"""Sandbox hardening tests: abuse of the protocol, resource limits, cleanup and misconfiguration.

Probes use the same trick as tests/test_sandbox.py: the builtins are reached through a lambda's
__globals__ so the static import screen is bypassed on purpose; the container must contain them.
Container classes skip with a visible reason when the runtime is missing.
"""

import json
from functools import partial
import os
import shutil
import subprocess
import time
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ddg import harness, sandbox
from ddg.demo import build_demo
from ddg.harness import FakeService, _drive_worker

observe = partial(harness.observe, path="src/job_client.py")  # the demo decision scope

BUILTINS = "(lambda: 0).__globals__['__builtins__']"
SYS = BUILTINS + "['__im' + 'port__']('s' + 'ys')"
OS = BUILTINS + "['__im' + 'port__']('o' + 's')"
CHECK = json.loads(Path("examples/manual_check.json").read_text(encoding="utf-8"))
HAVE_DOCKER = sandbox._usable("docker")
HAVE_PODMAN = sandbox._usable("podman")
PREFIX = "ddg-u7t-"  # test containers get their own prefix so parallel suites cannot confuse the leak check

GOOD = ("def submit_job(service, payload, operation_id):\n"
        "    r = service.create(payload, operation_id)\n"
        "    if r.status == 503:\n"
        "        e = service.lookup(operation_id)\n"
        "        if e: return e\n"
        "        r = service.create(payload, operation_id)\n"
        "    return r.job_id\n")


def _src(body: str) -> str:
    return "def submit_job(service, payload, operation_id):\n" + "".join(
        "    " + line + "\n" for line in body.strip("\n").split("\n"))


def _commit(repo: Path, source: str) -> None:
    (repo / "src" / "job_client.py").write_text(source, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "src/job_client.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=T", "-c", "user.email=t@e.invalid",
                    "commit", "--quiet", "-m", "fixture"], check=True)


def leftovers(runtime: str = "docker") -> str:
    return subprocess.run([runtime, "ps", "-aq", "--filter", f"name={PREFIX}"],
                          capture_output=True, text=True).stdout.strip()


def _tracked_name():
    return PREFIX + uuid.uuid4().hex[:12]


class ProtocolAbuse:
    """Shared cases; subclasses pick the sandbox mode."""
    mode = "host"
    runtime = None

    def run_source(self, source, timeout=30):
        with TemporaryDirectory() as folder, \
                patch.dict(os.environ, {"DDG_SANDBOX": self.mode}), \
                patch.object(sandbox, "new_name", _tracked_name):
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            _commit(repo, source)
            started = time.monotonic()
            result = observe(repo, "HEAD", CHECK, timeout=timeout)
            result["_elapsed"] = time.monotonic() - started
        if self.runtime:
            self.assertEqual(leftovers(self.runtime), "", "container leaked")
        return result

    def test_honest_client_still_passes(self):
        self.assertEqual(self.run_source(GOOD)["status"], "PASS")

    def test_stdout_flood_is_an_error_with_bounded_buffering(self):
        src = _src("o = " + OS + "\nchunk = b'x' * (1 << 20)\nwhile True:\n    o.write(1, chunk)")
        result = self.run_source(src, timeout=20)
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("size limit", result["error"])
        self.assertLess(result["_elapsed"], 20)

    def test_single_huge_protocol_line_is_an_error(self):
        src = _src("o = " + OS + "\n"
                   "o.write(1, b'{\"op\":\"x\",\"pad\":\"' + b'a' * (5 << 20) + b'\"}\\n')\n"
                   "while True:\n    pass")
        result = self.run_source(src, timeout=20)
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("size limit", result["error"])

    def test_flood_of_valid_calls_is_capped(self):
        src = _src("while True:\n    service.lookup(operation_id)")
        result = self.run_source(src, timeout=60)
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("too many messages", result["error"])

    def test_stderr_flood_does_not_disturb_the_result(self):
        src = _src("o = " + OS + "\nchunk = b'e' * (1 << 20)\n"
                   "import time\nend = time.monotonic() + 3\n"
                   "while time.monotonic() < end:\n    o.write(2, chunk)\n"
                   "r = service.create(payload, operation_id)\n"
                   "if r.status == 503:\n    return service.lookup(operation_id)\n"
                   "return r.job_id")
        self.assertEqual(self.run_source(src)["status"], "PASS")

    def test_target_that_closes_or_steals_stdin_is_an_error(self):
        cases = {
            "close_file": "sys = " + SYS + "\nsys.stdin.close()\nreturn service.lookup(operation_id)",
            "close_fd": "o = " + OS + "\no.close(0)\nreturn service.lookup(operation_id)",
        }
        for name, body in cases.items():
            with self.subTest(name):
                result = self.run_source(_src(body), timeout=15)
                self.assertEqual(result["status"], "ERROR", result)

    def test_target_that_reads_stdin_itself_cannot_hang_the_run(self):
        result = self.run_source(_src("sys = " + SYS + "\nsys.stdin.readline()\nreturn None"), timeout=4)
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("timed out", result["error"])

    def test_forged_done_message_cannot_produce_a_pass(self):
        src = _src("o = " + OS + "\no.write(1, b'{\"op\":\"done\",\"returned\":\"job-1\"}\\n')\n"
                   "while True:\n    pass")
        result = self.run_source(src, timeout=15)
        self.assertNotEqual(result["status"], "PASS", result)
        self.assertEqual(result["unique_jobs"] if result["status"] == "FAIL" else 0, 0)

    def test_garbage_on_the_protocol_fd_is_an_error(self):
        src = _src("o = " + OS + "\no.write(1, b'not json\\n')\nwhile True:\n    pass")
        result = self.run_source(src, timeout=15)
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("malformed", result["error"])

    def test_background_thread_outliving_submit_job_is_killed(self):
        src = GOOD.replace("    r = service.create(payload, operation_id)\n",
                           "    import threading\n"
                           "    def spin():\n        while True:\n            pass\n"
                           "    threading.Thread(target=spin).start()\n"
                           "    r = service.create(payload, operation_id)\n", 1)
        result = self.run_source(src, timeout=15)
        self.assertEqual(result["status"], "PASS", result)
        self.assertLess(result["_elapsed"], 14)

    def test_worker_crash_is_an_error(self):
        result = self.run_source(_src("o = " + OS + "\no._exit(3)"), timeout=15)
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("without a result", result["error"])


class HostProtocolAbuse(ProtocolAbuse, unittest.TestCase):
    mode = "host"


@unittest.skipUnless(HAVE_DOCKER, "no usable docker daemon; docker sandbox tests skipped")
class DockerProtocolAbuse(ProtocolAbuse, unittest.TestCase):
    mode = "docker"
    runtime = "docker"

    def test_fork_bomb_is_bounded_by_pids_limit_and_cleaned_up(self):
        src = _src("o = " + OS + "\nfor _ in range(500):\n"
                   "    try:\n        if o.fork() == 0:\n            while True:\n                pass\n"
                   "    except OSError:\n        break\n"
                   "r = service.create(payload, operation_id)\n"
                   "if r.status == 503:\n    return service.lookup(operation_id)\n"
                   "return r.job_id")
        result = self.run_source(src, timeout=30)
        # fork() failing with EAGAIN (pids-limit) is what lets the parent reach the post-probe path
        self.assertIsNone(result["error"], result)
        self.assertLess(result["_elapsed"], 30)

    def test_unbounded_fork_bomb_never_hangs_or_leaks(self):
        result = self.run_source(_src("o = " + OS + "\nwhile True:\n    o.fork()"), timeout=20)
        self.assertIn(result["status"], {"ERROR", "FAIL"})
        self.assertLess(result["_elapsed"], 20)

    def test_timeout_leaves_no_container_or_orphan(self):
        result = self.run_source(_src("while True:\n    pass"), timeout=5)
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("timed out", result["error"])

    def test_parent_raising_mid_run_still_removes_the_container(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"DDG_SANDBOX": "docker"}), \
                patch.object(sandbox, "new_name", _tracked_name):
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            _commit(repo, _src("while True:\n    pass"))
            with patch.object(harness, "threading", **{"Thread.side_effect": RuntimeError("boom")}):
                with self.assertRaises(RuntimeError):
                    observe(repo, "HEAD", CHECK, timeout=5)
        time.sleep(1)
        self.assertEqual(leftovers(), "")

    def test_immediate_reap_of_a_busy_container_does_not_race_container_creation(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"DDG_SANDBOX": "docker"}), \
                patch.object(sandbox, "new_name", _tracked_name):
            module = Path(folder) / "src" / "job_client.py"
            module.parent.mkdir()
            module.write_text("def submit_job(s, p, o):\n    while True:\n        pass\n", encoding="utf-8")
            worker = Path(harness.__file__).with_name("worker.py")
            for _ in range(4):
                proc, runtime, name = sandbox.launch(worker, module, Path(folder))
                sandbox.reap(proc, runtime, name)
        time.sleep(2)
        self.assertEqual(leftovers(), "")

    def test_unicode_and_spaced_temp_paths_mount(self):
        with TemporaryDirectory(prefix="ddg ünï çödé ") as folder, \
                patch.dict(os.environ, {"DDG_SANDBOX": "docker"}), patch.object(sandbox, "new_name", _tracked_name):
            root = Path(folder).resolve()
            module = root / "sr c" / "job_client.py"
            module.parent.mkdir()
            module.write_text(GOOD, encoding="utf-8")
            worker = root / "wörker dir" / "worker.py"
            worker.parent.mkdir()
            shutil.copy(Path(harness.__file__).with_name("worker.py"), worker)
            proc, runtime, name = sandbox.launch(worker, module, root)
            try:
                outcome = _drive_worker(proc, FakeService("none"))
            finally:
                sandbox.reap(proc, runtime, name)
        self.assertEqual(outcome["op"], "done", outcome)
        self.assertEqual(leftovers(), "")


@unittest.skipUnless(HAVE_DOCKER, "no usable docker daemon; docker inspect tests skipped")
class InspectedLimitTests(unittest.TestCase):
    def test_started_container_really_has_the_limits(self):
        with TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "src").mkdir()
            (root / "src" / "m.py").write_text("", encoding="utf-8")
            (root / "sleep.py").write_text("import time\ntime.sleep(120)\n", encoding="utf-8")
            name = _tracked_name()
            sandbox.ensure_image("docker")
            argv = sandbox.container_argv("docker", name, root / "src", root / "sleep.py", "m.py")
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            try:
                info = None
                for _ in range(60):
                    shown = subprocess.run(["docker", "inspect", name], capture_output=True, text=True)
                    if shown.returncode == 0 and json.loads(shown.stdout)[0]["State"]["Running"]:
                        info = json.loads(shown.stdout)[0]
                        break
                    time.sleep(0.5)
                self.assertIsNotNone(info, "container never started")
                host = info["HostConfig"]
                self.assertEqual(host["NetworkMode"], "none")
                self.assertIs(host["ReadonlyRootfs"], True)
                self.assertEqual([c.upper() for c in host["CapDrop"]], ["ALL"])
                self.assertFalse(host["CapAdd"])
                self.assertIs(host["Privileged"], False)
                self.assertEqual(host["Memory"], 128 * 1024 * 1024)
                self.assertEqual(host["MemorySwap"], 128 * 1024 * 1024)
                self.assertEqual(host["PidsLimit"], 64)
                self.assertEqual(host["NanoCpus"], 500_000_000)
                self.assertTrue(any(o.startswith("no-new-privileges") for o in host["SecurityOpt"]))
                self.assertEqual(info["Config"]["User"], "65534:65534")
                self.assertIn("/tmp", host["Tmpfs"])
                self.assertIn("noexec", host["Tmpfs"]["/tmp"])
                self.assertTrue(all(not m.get("RW", False) for m in info["Mounts"]), info["Mounts"])
            finally:
                sandbox.force_remove("docker", name)
                proc.kill()
                proc.wait()
                proc.stdin.close()
        self.assertEqual(leftovers(), "")


class ArgvPinTests(unittest.TestCase):
    def test_exact_flag_set_is_pinned(self):
        """Loosening any flag (or adding one) must fail CI and be a conscious decision."""
        argv = sandbox.container_argv("docker", "ddg-x", Path("/s"), Path("/w.py"), "m.py")
        self.assertEqual(argv, [
            "docker", "run", "--rm", "-i", "--name", "ddg-x",
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "64", "--memory", "128m", "--memory-swap", "128m", "--cpus", "0.5",
            "--user", "65534:65534",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
            "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "PYTHONIOENCODING=utf-8",
            "-v", f"{Path('/s')}:/work/src:ro", "-v", f"{Path('/w.py')}:/work/worker.py:ro",
            sandbox.DEFAULT_IMAGE, "python", "/work/worker.py", "/work/src/m.py"])

    def test_podman_uses_the_same_flags(self):
        docker = sandbox.container_argv("docker", "n", Path("/s"), Path("/w.py"), "m.py")
        podman = sandbox.container_argv("podman", "n", Path("/s"), Path("/w.py"), "m.py")
        self.assertEqual(podman[0], "podman")
        self.assertEqual(podman[1:], docker[1:])


DIGEST = "sha256:" + "a" * 64


class ImageTests(unittest.TestCase):
    def env(self, **values):
        base = {"DDG_SANDBOX_IMAGE": "", "DDG_SANDBOX_ALLOW_UNPINNED": ""}
        base.update(values)
        return patch.dict(os.environ, base)

    def test_default_is_unpinned_and_says_so(self):
        with self.env(DDG_SANDBOX="docker"), patch.object(sandbox, "_usable", return_value=True):
            info = sandbox.describe()
        self.assertEqual((info["mode"], info["image"], info["pinned"]),
                         ("docker", sandbox.DEFAULT_IMAGE, False))
        self.assertIn("NOT digest-pinned", info["note"])

    def test_digest_pinned_override_is_accepted_and_reported_pinned(self):
        ref = "registry.example/ddg/sandbox@" + DIGEST
        with self.env(DDG_SANDBOX="podman", DDG_SANDBOX_IMAGE=ref), patch.object(sandbox, "_usable", return_value=True):
            info = sandbox.describe()
            self.assertEqual(sandbox.image(), ref)
        self.assertEqual((info["mode"], info["image"], info["pinned"]), ("podman", ref, True))

    def test_unpinned_override_needs_the_dev_flag(self):
        with self.env(DDG_SANDBOX_IMAGE="ddg-sandbox:dev"):
            with self.assertRaises(sandbox.SandboxUnavailable) as caught:
                sandbox.image()
            self.assertIn("ALLOW_UNPINNED", str(caught.exception))
        with self.env(DDG_SANDBOX_IMAGE="ddg-sandbox:dev", DDG_SANDBOX_ALLOW_UNPINNED="1", DDG_SANDBOX="docker"), \
                patch.object(sandbox, "_usable", return_value=True):
            self.assertEqual(sandbox.image(), "ddg-sandbox:dev")
            info = sandbox.describe()
        self.assertFalse(info["pinned"])
        self.assertIn("dev override", info["note"])

    def test_malformed_or_option_like_references_are_rejected_even_with_the_flag(self):
        for bad in ("--privileged", "-v /:/host", "img with space", "img;rm", "img\nx", "@sha256:abc"):
            with self.subTest(bad), self.env(DDG_SANDBOX_IMAGE=bad, DDG_SANDBOX_ALLOW_UNPINNED="1"):
                with self.assertRaises(sandbox.SandboxUnavailable):
                    sandbox.image()

    def test_bad_image_override_fails_closed_through_observe(self):
        with TemporaryDirectory() as folder, \
                patch.dict(os.environ, {"DDG_SANDBOX": "docker", "DDG_SANDBOX_IMAGE": "--privileged"}), \
                patch.object(sandbox, "_usable", return_value=True):
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            result = observe(repo, "HEAD", CHECK)
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("image reference", result["error"])

    def test_host_mode_is_described_as_unsafe(self):
        with self.env(DDG_SANDBOX="host"):
            info = sandbox.describe()
        self.assertEqual((info["mode"], info["pinned"]), ("host", False))
        self.assertIn("UNSAFE", info["note"])


class MisconfigurationTests(unittest.TestCase):
    def observe_with(self, mode):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"DDG_SANDBOX": mode}), \
                patch.object(sandbox, "_usable", return_value=False):
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            return observe(repo, "HEAD", CHECK)

    def test_unknown_value_names_the_value(self):
        result = self.observe_with("chroot")
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("chroot", result["error"])

    def test_docker_selected_but_daemon_down_is_a_clear_error(self):
        result = self.observe_with("docker")
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("docker", result["error"])
        self.assertIn("not running", result["error"])

    def test_podman_requested_but_absent_is_a_clear_error(self):
        with patch.dict(os.environ, {"DDG_SANDBOX": "podman"}), \
                patch.object(sandbox.shutil, "which", return_value=None):
            sandbox._usable.cache_clear()
            try:
                with self.assertRaises(sandbox.SandboxUnavailable) as caught:
                    sandbox.resolve()
            finally:
                sandbox._usable.cache_clear()
        self.assertIn("podman", str(caught.exception))
        with patch.dict(os.environ, {"DDG_SANDBOX": "podman"}), patch.object(sandbox, "_usable", return_value=False):
            info = sandbox.describe()
        self.assertEqual(info["mode"], "unavailable")
        self.assertIn("podman", info["note"])

    def test_auto_with_no_runtime_never_falls_back_to_host(self):
        with patch.dict(os.environ, {"DDG_SANDBOX": "auto"}), patch.object(sandbox, "_usable", return_value=False):
            with self.assertRaises(sandbox.SandboxUnavailable):
                sandbox.resolve()


class EnsureImageTests(unittest.TestCase):
    def setUp(self):
        sandbox._ensure_image.cache_clear()
        self.addCleanup(sandbox._ensure_image.cache_clear)
        env = patch.dict(os.environ, {"DDG_SANDBOX_IMAGE": ""})
        env.start()
        self.addCleanup(env.stop)

    @staticmethod
    def done(code):
        return subprocess.CompletedProcess([], code, b"", b"")

    def test_inspect_timeout_fails_closed(self):
        with patch.object(sandbox.subprocess, "run", side_effect=subprocess.TimeoutExpired("docker", 30)):
            with self.assertRaises(sandbox.SandboxUnavailable):
                sandbox.ensure_image("docker")

    def test_pull_failure_fails_closed_and_is_not_cached(self):
        with patch.object(sandbox.subprocess, "run", side_effect=[self.done(1), self.done(1)]):
            with self.assertRaises(sandbox.SandboxUnavailable) as caught:
                sandbox.ensure_image("docker")
        self.assertIn("pull", str(caught.exception))
        with patch.object(sandbox.subprocess, "run", side_effect=[self.done(1), self.done(0)]) as run:
            sandbox.ensure_image("docker")  # the earlier failure must not be remembered
            self.assertEqual(run.call_count, 2)

    def test_runtime_vanishing_fails_closed(self):
        with patch.object(sandbox.subprocess, "run", side_effect=FileNotFoundError("docker")):
            with self.assertRaises(sandbox.SandboxUnavailable):
                sandbox.ensure_image("docker")

    def test_success_is_cached_per_image(self):
        with patch.object(sandbox.subprocess, "run", return_value=self.done(0)) as run:
            sandbox.ensure_image("docker")
            sandbox.ensure_image("docker")
            self.assertEqual(run.call_count, 1)
            with patch.dict(os.environ, {"DDG_SANDBOX_IMAGE": "x@" + DIGEST}):
                sandbox.ensure_image("docker")
            self.assertEqual(run.call_count, 2)


class DriverLimitTests(unittest.TestCase):
    def test_flood_of_small_valid_messages_is_cut_off(self):
        line = json.dumps({"op": "lookup", "operation_id": "x"}) + "\n"

        class Proc:
            class stdout:
                @staticmethod
                def readline(limit):
                    return line

            class stdin:
                @staticmethod
                def write(_):
                    pass

                @staticmethod
                def flush():
                    pass

            def poll(self):
                return None

        service = FakeService("none")
        outcome = _drive_worker(Proc(), service)
        self.assertEqual(outcome["op"], "error")
        self.assertLessEqual(len(service.events), harness._MAX_MESSAGES)

    def test_parent_exception_reaps_in_host_mode_too(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"DDG_SANDBOX": "host"}):
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            with patch.object(harness, "threading", **{"Thread.side_effect": RuntimeError("boom")}), \
                    patch.object(sandbox, "reap", wraps=sandbox.reap) as reap:
                with self.assertRaises(RuntimeError):
                    observe(repo, "HEAD", CHECK)
        reap.assert_called_once()


@unittest.skipUnless(HAVE_PODMAN, "podman not installed or not usable; podman parity tests skipped")
class PodmanParityTests(unittest.TestCase):
    def test_honest_client_passes_under_podman(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"DDG_SANDBOX": "podman"}):
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            _commit(repo, GOOD)
            self.assertEqual(observe(repo, "HEAD", CHECK, timeout=60)["status"], "PASS")
        self.assertEqual(leftovers("podman"), "")

    def test_network_and_filesystem_probes_are_contained_under_podman(self):
        src = _src("s = " + BUILTINS + "['__im' + 'port__']('soc' + 'ket')\n"
                   "try:\n    s.create_connection(('1.1.1.1', 53), timeout=3)\n    return 'ESCAPED'\n"
                   "except OSError:\n    pass\n"
                   "try:\n    " + BUILTINS + "['op' + 'en']('/work/src/pwn', 'w').write('x')\n    return 'ESCAPED'\n"
                   "except OSError:\n    pass\n"
                   "return service.create(payload, operation_id).job_id")
        with TemporaryDirectory() as folder, patch.dict(os.environ, {"DDG_SANDBOX": "podman"}):
            repo = Path(build_demo(Path(folder) / "repo")["repo"])
            _commit(repo, src)
            result = observe(repo, "HEAD", CHECK, timeout=60)
        self.assertIsNone(result["error"], result)
        self.assertNotEqual(result["returned_job_id"], "ESCAPED")


if __name__ == "__main__":
    unittest.main()
