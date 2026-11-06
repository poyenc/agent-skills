#!/usr/bin/env python3
"""Minimal unit tests for the parsing/mapping functions, with canned inputs.

Run with: python3 scripts/test_gpu_usage.py
"""

import contextlib
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gpu_collector as gc  # noqa: E402
import gpu_usage as gu  # noqa: E402

# Canned rocm-smi output, same shape as observed on heliosr-e15-13.
ROCM_SMI_SAMPLE = """
GPU[0]\t\t: GPU use (%): 0
GPU[1]\t\t: GPU use (%): 97
GPU[0]\t\t: VRAM Total Memory (B): 463856467968
GPU[0]\t\t: VRAM Total Used Memory (B): 179011584
GPU[1]\t\t: VRAM Total Memory (B): 463856467968
GPU[1]\t\t: VRAM Total Used Memory (B): 50179011584
GPU[0]\t\t: Temperature (Sensor junction) (C): 71.565
GPU[1]\t\t: Temperature (Sensor junction) (C): 73.412
GPU[0]\t\t: Current Socket Graphics Package Power (W): 1112.646
GPU[1]\t\t: Current Socket Graphics Package Power (W): 1129.877
GPU[0]\t\t: sclk clock level: 1: (2233Mhz)
GPU[1]\t\t: sclk clock level: 1: (2256Mhz)
"""

ROCM_SMI_UNIQUEID = """
GPU[0]\t\t: Unique ID: 0x781eb2510b4fcc38
GPU[1]\t\t: Unique ID: 0x5c70f0ba29843303
"""

# Canned KFD topology, values taken verbatim from a live heliosr-e15-13 read.
TOPOLOGY = {
    56179: {"render_minor": 128, "unique_id_dec": 8655551595004546104, "node": 2},
    39772: {"render_minor": 152, "unique_id_dec": 6661088531232076547, "node": 5},
}


class TestRocmSmiParsing(unittest.TestCase):
    def test_parse_sample(self):
        parsed = gc.parse_rocm_smi_sample(ROCM_SMI_SAMPLE)
        self.assertEqual(parsed[0]["util_pct"], 0)
        self.assertEqual(parsed[1]["util_pct"], 97)
        self.assertEqual(parsed[1]["vram_used_bytes"], 50179011584)
        self.assertAlmostEqual(parsed[0]["temp_c"], 71.565)
        self.assertEqual(parsed[1]["sclk_mhz"], 2256)

    def test_parse_uniqueid(self):
        parsed = gc.parse_rocm_smi_uniqueid(ROCM_SMI_UNIQUEID)
        self.assertEqual(parsed, {0: "0x781eb2510b4fcc38", 1: "0x5c70f0ba29843303"})


class TestGpuIdMapping(unittest.TestCase):
    def test_exact_hex_join(self):
        uid_map = gc.parse_rocm_smi_uniqueid(ROCM_SMI_UNIQUEID)
        mapping, assumed = gc.map_gpu_id_to_rocm_index(TOPOLOGY, uid_map)
        self.assertFalse(assumed)
        self.assertEqual(mapping, {56179: 0, 39772: 1})

    def test_fallback_when_no_match(self):
        mapping, assumed = gc.map_gpu_id_to_rocm_index(TOPOLOGY, {})
        self.assertTrue(assumed)
        self.assertEqual(mapping, {39772: 0, 56179: 1})  # sorted gpu_id order


class TestCgroupParsing(unittest.TestCase):
    def test_docker_cgroup_v2(self):
        raw = "0::/system.slice/docker-7bef543c4896889d6b688f4b51b58769bebdee8fa5596c20ce63d9f9e31b10e1.scope\n"
        # exercise the same regexes _cgroup_info uses, without touching /proc
        import re

        m = re.search(r"docker-([0-9a-f]{12,64})\.scope", raw)
        self.assertEqual(m.group(1)[:12], "7bef543c4896")

    def test_slurm_job_cgroup(self):
        raw = "0::/system.slice/slurmstepd.scope/job_12345/step_0\n"
        import re

        m = re.search(r"/job_(\d+)", raw)
        self.assertEqual(m.group(1), "12345")


class TestLockDetection(unittest.TestCase):
    def test_geak_lock_pattern_matches(self):
        # GEAK's gpu_lock.sh: LOCK_FILE="${LOCK_DIR}/gpu_${GPU_ID}.lock" under /tmp/team_gpu_locks
        self.assertTrue(gc._SPECIFIC_LOCK_RE.search("/tmp/team_gpu_locks/gpu_0.lock"))
        self.assertFalse(gc._SPECIFIC_LOCK_RE.search("/tmp/some_other_file"))

    def test_generic_lock_pattern(self):
        self.assertTrue(gc._GENERIC_LOCK_RE.search("/var/lock/myteam.lock"))
        self.assertFalse(gc._GENERIC_LOCK_RE.search("/home/user/not_a_lock_dir/file"))


class TestOursClassification(unittest.TestCase):
    def test_container_name_match(self):
        self.assertTrue(gu.classify_ours("123", {}, "poyenc-rocisa-trans-collision-e15-13", ["poyenc-rocisa-trans-collision-e15-13"]))
        self.assertFalse(gu.classify_ours("123", {}, "junlin12_dev_hstu", ["poyenc-rocisa-trans-collision-e15-13"]))

    def test_pid_regex_match(self):
        self.assertTrue(gu.classify_ours("4242", {}, None, [r"^42"]))
        self.assertFalse(gu.classify_ours("5242", {}, None, [r"^42"]))


class TestOwnerInference(unittest.TestCase):
    def test_home_mount_plain(self):
        containers = {"abc": {"home_mounts": ["/home/poyechen/workspace/x"]}}
        occ = {"docker_id": "abc", "container": "c", "user": "root"}
        owner, inferred = gu._infer_owner_contact(occ, containers)
        self.assertEqual(owner, "poyechen")
        self.assertTrue(inferred)

    def test_home_mount_domain_prefixed(self):
        containers = {"abc": {"home_mounts": ["/home/AMD/kusjain/Kush/MBDG-AI-git"]}}
        occ = {"docker_id": "abc", "container": "c", "user": "root"}
        owner, inferred = gu._infer_owner_contact(occ, containers)
        self.assertEqual(owner, "kusjain")

    def test_collector_resolved_container_owner_wins(self):
        containers = {"abc": {"owner_user": "ginolu12", "owner_evidence": "container env USER=ginolu12",
                              "home_mounts": ["/home/other/x"]}}
        occ = {"docker_id": "abc", "container": "mi450_c", "user": "root"}
        self.assertEqual(gu._infer_owner_contact(occ, containers), ("ginolu12", True))
        self.assertEqual(gu._owner_label(occ, containers), "ginolu12 [mi450_c]")

    def test_collector_resolved_host_process_owner(self):
        occ = {"docker_id": None, "container": None, "user": "root",
               "owner_user": "junlin12", "owner_evidence": "ancestor sshd (pid 7)"}
        self.assertEqual(gu._infer_owner_contact(occ, {}), ("junlin12", True))

    def test_format_who_one_line_per_gpu_in_kfd_order(self):
        def gpu(gpu_id, index, pids):
            return {"gpu_id": gpu_id, "kfd_index": index, "rocm_index": None, "rocm_index_assumed": True,
                    "render_minor": 128, "card": None, "duty_cycle": 1.0 if pids else 0.0,
                    "samples": [{"pids": {p: 1 for p in pids}}]}
        data = {"gpus": [gpu(9367, 1, ["42"]), gpu(56179, 0, [])],
                "pids": {"42": {"user": "root", "cmd": "./fmha_new", "docker_id": "abc", "elapsed_s": 30.0}},
                "containers": {"abc": {"name": "mi450_c", "owner_user": "hao-iho2", "owner_evidence": "bind mount"}}}
        out = gu.format_who([{"host": "h", "status": "ok", "data": data}], [])
        self.assertEqual(out.splitlines(), [
            "h",
            "  GPU 0 (gpu_id 56179): free",
            "  GPU 1 (gpu_id 9367): hao-iho2 [container mi450_c, pid 42, 30s] ./fmha_new",
        ])

    def test_no_hints_at_all(self):
        occ = {"docker_id": None, "container": None, "user": "root"}
        owner, inferred = gu._infer_owner_contact(occ, {})
        self.assertIn("could not determine", owner)


class TestHistory(unittest.TestCase):
    def test_continuous_run(self):
        history = [
            {"ts": 100.0, "host": "h", "gpu_id": 1, "owner": "alice", "foreign": True},
            {"ts": 101.0, "host": "h", "gpu_id": 1, "owner": "alice", "foreign": True},
            {"ts": 102.0, "host": "h", "gpu_id": 1, "owner": "bob", "foreign": True},
        ]
        run = gu.continuous_run(history, "h", 1)
        self.assertEqual(run["owner"], "bob")
        self.assertEqual(run["first_seen"], 102.0)
        self.assertEqual(run["duration_s"], 0.0)

    def test_no_history(self):
        self.assertIsNone(gu.continuous_run([], "h", 1))


class TestKfdOnlySysfsParsing(unittest.TestCase):
    def test_parse_active_sclk_mhz(self):
        pp_dpm_sclk = "0: 300Mhz\n1: 1200Mhz *\n2: 2200Mhz\n"
        self.assertEqual(gc._parse_active_sclk_mhz(pp_dpm_sclk), 1200)

    def test_parse_active_sclk_mhz_no_marker(self):
        self.assertIsNone(gc._parse_active_sclk_mhz("0: 300Mhz\n1: 1200Mhz\n"))


class TestRocmSmiOptIn(unittest.TestCase):
    """Remote hosts must default to KFD-only: no rocm-smi/amd-smi invocation
    unless the caller explicitly opts in with --rocm-smi."""

    def test_remote_default_is_kfd_only(self):
        self.assertFalse(gu._use_rocm_smi_for_host("heliosr-e15-13", opt_in=False))

    def test_local_default_is_kfd_only(self):
        self.assertFalse(gu._use_rocm_smi_for_host(None, opt_in=False))

    def test_explicit_opt_in_applies_to_local(self):
        self.assertTrue(gu._use_rocm_smi_for_host(None, opt_in=True))

    def test_explicit_opt_in_applies_to_remote(self):
        self.assertTrue(gu._use_rocm_smi_for_host("heliosr-e15-13", opt_in=True))

    def test_remote_command_has_no_rocm_smi_or_amd_smi_substring_by_default(self):
        use_rocm_smi = gu._use_rocm_smi_for_host("heliosr-e15-13", opt_in=False)
        collector_args = gu._build_collector_args(5, 1.0, "GPUUSAGE_MARK", use_rocm_smi)
        full_cmd = gu._build_remote_cmd("heliosr-e15-13", collector_args)
        full_cmd_text = " ".join(full_cmd).lower()
        self.assertNotIn("rocm-smi", full_cmd_text)
        self.assertNotIn("amd-smi", full_cmd_text)

    def test_remote_command_includes_rocm_smi_flag_when_opted_in(self):
        use_rocm_smi = gu._use_rocm_smi_for_host("heliosr-e15-13", opt_in=True)
        collector_args = gu._build_collector_args(5, 1.0, "GPUUSAGE_MARK", use_rocm_smi)
        self.assertIn("--rocm-smi", collector_args)


class TestNoGpuHost(unittest.TestCase):
    def test_markdown_reports_no_gpus_cleanly(self):
        # Simulates what a login node with no rocm-smi/GPUs produces.
        host_results = [
            {
                "host": "login-node",
                "status": "ok",
                "data": {"errors": ["rocm-smi not found on PATH or under /opt/rocm*/bin"], "gpus": [], "pids": {}, "containers": {}},
            }
        ]
        out = gu.format_markdown(host_results, [], None)
        self.assertIn("No GPUs/rocm-smi found on this host.", out)
        self.assertIn("rocm-smi not found", out)


class TestKfdQueueAttribution(unittest.TestCase):
    """A pid occupies exactly the GPUs named by its live KFD queues; unreadable queues are never "free"."""

    GPU_IDS = [100 + i for i in range(8)]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = os.path.join(tmp.name, "proc")
        patcher = mock.patch.object(gc, "KFD_PROC", self.base)
        patcher.start()
        self.addCleanup(patcher.stop)

    def add_pid(self, pid, queue_gpu_ids, vram=4096):
        """Queues name queue_gpu_ids; vram_<gpu_id> exists for all 8 GPUs, as for a process that merely opened them."""
        pid_dir = os.path.join(self.base, str(pid))
        for i, gpu_id in enumerate(queue_gpu_ids):
            os.makedirs(os.path.join(pid_dir, "queues", str(i)))
            with open(os.path.join(pid_dir, "queues", str(i), "gpuid"), "w") as f:
                f.write(f"{gpu_id}\n")
        os.makedirs(pid_dir, exist_ok=True)
        for gpu_id in self.GPU_IDS:
            with open(os.path.join(pid_dir, f"vram_{gpu_id}"), "w") as f:
                f.write(f"{vram}\n")

    @contextlib.contextmanager
    def deny(self, listing=False, gpuid=False, sudo=None):
        """Direct reads of the queue listing / gpuid files raise PermissionError; sudo -n answers via sudo(cmd)."""
        real_listdir, real_open = os.listdir, open

        def listdir(path):
            if listing and str(path).endswith("/queues"):
                raise PermissionError(path)
            return real_listdir(path)

        def opener(path, *args, **kwargs):
            if gpuid and str(path).endswith("/gpuid"):
                raise PermissionError(path)
            return real_open(path, *args, **kwargs)

        with mock.patch.object(gc.os, "listdir", listdir), mock.patch.object(gc, "open", opener, create=True), \
                mock.patch.object(gc, "_run", lambda cmd, timeout=10.0: sudo(cmd) if sudo else ("", 1)):
            yield

    def test_pid_listed_only_on_the_gpu_of_its_queue(self):
        self.add_pid(7, [self.GPU_IDS[3]])
        result, unreadable = gc.sample_kfd_proc()
        self.assertEqual(result, {self.GPU_IDS[3]: {7: 4096}})
        self.assertEqual(unreadable, set())

    def test_pid_with_queues_on_two_gpus_lists_both(self):
        self.add_pid(7, [self.GPU_IDS[1], self.GPU_IDS[6], self.GPU_IDS[6]])
        result, _ = gc.sample_kfd_proc()
        self.assertEqual(sorted(result), [self.GPU_IDS[1], self.GPU_IDS[6]])

    def test_pid_without_queues_occupies_nothing(self):
        self.add_pid(7, [])
        self.assertEqual(gc.sample_kfd_proc(), ({}, set()))

    def test_denied_queue_listing_resolved_with_sudo(self):
        self.add_pid(7, [self.GPU_IDS[2]])
        with self.deny(listing=True, sudo=lambda cmd: ("0\n", 0) if cmd[:3] == ["sudo", "-n", "ls"] else ("", 1)):
            result, unreadable = gc.sample_kfd_proc()
        self.assertEqual(result, {self.GPU_IDS[2]: {7: 4096}})
        self.assertEqual(unreadable, set())

    def test_denied_gpuid_resolved_with_sudo(self):
        self.add_pid(7, [self.GPU_IDS[2], self.GPU_IDS[5]])
        with self.deny(gpuid=True, sudo=lambda cmd: (f"{self.GPU_IDS[2]}\n{self.GPU_IDS[5]}\n", 0)):
            result, unreadable = gc.sample_kfd_proc()
        self.assertEqual(sorted(result), [self.GPU_IDS[2], self.GPU_IDS[5]])
        self.assertEqual(unreadable, set())

    def test_denied_queue_listing_with_failed_sudo_is_unreadable_not_empty(self):
        self.add_pid(7, [self.GPU_IDS[2]])
        with self.deny(listing=True):
            self.assertEqual(gc.sample_kfd_proc(), ({}, {7}))

    def test_denied_gpuid_with_failed_sudo_is_unreadable_not_empty(self):
        self.add_pid(7, [self.GPU_IDS[2]])
        with self.deny(gpuid=True):
            self.assertEqual(gc.sample_kfd_proc(), ({}, {7}))

    def test_exited_pid_is_not_unreadable(self):
        self.add_pid(7, [self.GPU_IDS[2]])
        real_listdir = os.listdir

        def vanishing(path):
            if str(path).endswith("/queues"):
                raise PermissionError(path)
            return real_listdir(path)

        def exits_while_sudo_runs(cmd, timeout=10.0):
            os.rename(os.path.join(self.base, "7"), os.path.join(self.base, "gone"))
            return "", 2

        with mock.patch.object(gc.os, "listdir", vanishing), mock.patch.object(gc, "_run", exits_while_sudo_runs):
            self.assertEqual(gc.sample_kfd_proc(), ({}, set()))

    def test_unreadable_pid_is_never_printed_free(self):
        gpu = {"gpu_id": 101, "kfd_index": 1, "rocm_index": None, "rocm_index_assumed": True, "render_minor": 128,
               "card": None, "duty_cycle": 0.0, "samples": [{"pids": {}}], "queue_unreadable_pids": ["42"]}
        data = {"gpus": [gpu], "containers": {},
                "pids": {"42": {"user": "root", "cmd": "./bench", "owner_user": "alice", "owner_evidence": "process loginuid"}}}
        out = gu.format_who([{"host": "h", "status": "ok", "data": data}], [])
        self.assertIn("alice", out)
        self.assertIn("KFD queues not readable", out)
        self.assertNotIn("free", out)
        self.assertNotIn("free", gu.summarize_gpu(gpu, data["pids"], {}, [])["state"])


def _fake_pwd():
    users = {"root": 0, "alice": 1001, "bob": 1002}
    mod = types.ModuleType("pwd")

    def entry(name):
        return types.SimpleNamespace(pw_name=name, pw_uid=users[name])

    def getpwnam(name):
        if name not in users:
            raise KeyError(name)
        return entry(name)

    def getpwuid(uid):
        for name, u in users.items():
            if u == uid:
                return entry(name)
        raise KeyError(uid)

    mod.getpwnam, mod.getpwuid = getpwnam, getpwuid
    return mod


CONTAINER_ID = "7bef543c4896889d6b688f4b51b58769bebdee8fa5596c20ce63d9f9e31b10e1"


def _proc_files(pid, uid=0, loginuid=None, cgroup=None, ppid=1):
    """Canned /proc/<pid> files of a running process (stat start time 1000 ticks)."""
    files = {
        f"/proc/{pid}/stat": f"{pid} (python3) S {ppid} {pid} {pid} 0 " + " ".join(["0"] * 14) + " 1000 0\n",
        f"/proc/{pid}/status": f"Name:\tpython3\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n",
        f"/proc/{pid}/cmdline": "python3\0train.py\0",
    }
    if loginuid is not None:
        files[f"/proc/{pid}/loginuid"] = f"{loginuid}\n"
    if cgroup:
        files[f"/proc/{pid}/cgroup"] = f"0::/system.slice/docker-{cgroup}.scope\n"
    return files


class TestOwnerResolution(unittest.TestCase):
    """GPU PID -> cgroup -> docker inspect -> login person, on a fake /proc and injected command runner."""

    def host(self, files, commands):
        """commands: {substring of the command line: (stdout, returncode)}; anything else fails (rc 1)."""
        def run(cmd, timeout=10.0):
            line = " ".join(cmd)
            for key, result in commands.items():
                if key in line:
                    return result
            return "", 1

        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.dict(sys.modules, {"pwd": _fake_pwd()}))
        stack.enter_context(mock.patch.object(gc, "_read", lambda path: files.get(path)))
        stack.enter_context(mock.patch.object(gc, "_read_privileged", lambda path: (files.get(path), None if path in files else "absent")))
        stack.enter_context(mock.patch.object(gc, "_run", run))

    def inspect_json(self, name, mounts=(), env=(), labels=None, init_pid=900):
        return "|||".join([json.dumps(labels or {}), json.dumps(list(env)), json.dumps([{"Source": m} for m in mounts]),
                           "2026-11-07T01:00:00.1Z", str(init_pid), "2026-11-07T01:00:01Z", "/" + name])

    def container_line(self, name):
        return f"{CONTAINER_ID} {name} img 2026-11-07 01:00:00 +0000 UTC\n"

    def who_line(self, pid, files, commands, ours=()):
        """Run the collector's per-pid chain, then render the one line gpu_usage prints for it."""
        self.host(files, commands)
        pinfo = gc.collect_pid_info(pid, 0.0)
        containers = {}
        if pinfo.get("docker_id"):
            ps = gc.docker_ps_map()
            meta = dict(ps.get(pinfo["docker_id"], {}))
            meta.update(gc.docker_inspect_details(meta.get("name") or pinfo["docker_id"], pinfo.get("loginuid_user")))
            containers[pinfo["docker_id"]] = meta
        gpu = {"gpu_id": 9367, "kfd_index": 0, "rocm_index": None, "rocm_index_assumed": True, "render_minor": 128,
               "card": None, "duty_cycle": 1.0, "samples": [{"pids": {str(pid): 1}}]}
        data = {"gpus": [gpu], "pids": {str(pid): pinfo}, "containers": containers}
        return gu.format_who([{"host": "h", "status": "ok", "data": data}], []).splitlines()[1], pinfo, containers

    def test_root_in_alice_container_with_bobs_mount_is_alice(self):
        files = _proc_files(4242, cgroup=CONTAINER_ID, loginuid=1001)
        commands = {"docker ps": (self.container_line("alice-dev"), 0),
                    "docker inspect": (self.inspect_json("alice-dev", mounts=["/home/bob/data"]), 0),
                    "stat -c": ("bob\n", 0)}
        line, _, _ = self.who_line(4242, files, commands)
        self.assertTrue(line.startswith("  GPU 0 (gpu_id 9367): alice [container alice-dev, pid 4242"), line)

    def test_container_owner_prefers_gpu_process_loginuid_over_bobs_mount(self):
        self.host({}, {"docker inspect": (self.inspect_json("alice-dev", mounts=["/home/bob/data"]), 0), "stat -c": ("bob\n", 0)})
        meta = gc.docker_inspect_details("alice-dev", "alice")
        self.assertEqual((meta["owner_user"], meta["owner_evidence"]), ("alice", "loginuid of the GPU process"))

    def init_loginuid_denied(self, sudo_result, mounts=("/home/bob/data",)):
        """Init pid 900 (no KFD dir): its loginuid is denied directly; sudo answers with sudo_result."""
        self.host({}, {"docker inspect": (self.inspect_json("shared", mounts=mounts, init_pid=900), 0), "stat -c": ("bob\n", 0),
                       "cat /proc/900/loginuid": sudo_result})
        real_stat = os.stat

        def stat(path, *args, **kwargs):
            if str(path).startswith("/proc/900/"):
                raise PermissionError(path)
            return real_stat(path, *args, **kwargs)

        with mock.patch.object(gc.os, "stat", stat):
            return gc.docker_inspect_details("shared", None)

    def test_init_loginuid_read_with_sudo_when_proc_denies_it(self):
        meta = self.init_loginuid_denied(("1001\n", 0))
        self.assertEqual((meta["owner_user"], meta["owner_evidence"]), ("alice", "loginuid of the container init process"))

    def test_init_loginuid_denied_and_sudo_failed_falls_to_the_next_evidence(self):
        meta = self.init_loginuid_denied(("", 1))
        self.assertEqual(meta["owner_user"], "bob")
        self.assertIn("bind mount", meta["owner_evidence"])

    def test_init_loginuid_denied_and_sudo_failed_without_other_evidence_is_an_error(self):
        meta = self.init_loginuid_denied(("", 1), mounts=())
        self.assertIsNone(meta["owner_user"])
        self.assertIn("no login account found", meta["owner_error"])

    def init_loginuid_hidden(self, sudo_result, init_pid=900):
        """Hidepid=2: direct read and stat of the init pid's files are absent; docker inspect says the container runs."""
        self.host({}, {"docker inspect": (self.inspect_json("shared", mounts=["/home/bob/data"], init_pid=init_pid), 0),
                       "stat -c": ("bob\n", 0), f"cat /proc/{init_pid}/loginuid": sudo_result})
        real_stat = os.stat

        def stat(path, *args, **kwargs):
            if str(path).startswith(f"/proc/{init_pid}/"):
                raise FileNotFoundError(path)
            return real_stat(path, *args, **kwargs)

        with mock.patch.object(gc.os, "stat", stat):
            return gc.docker_inspect_details("shared", None)

    def test_hidepid2_init_loginuid_read_with_sudo_because_inspect_says_it_is_live(self):
        meta = self.init_loginuid_hidden(("1001\n", 0))
        self.assertEqual((meta["owner_user"], meta["owner_evidence"]), ("alice", "loginuid of the container init process"))

    def test_hidepid2_init_loginuid_with_sudo_failed_invents_no_name(self):
        meta = self.init_loginuid_hidden(("", 1))
        self.assertEqual(meta["owner_user"], "bob")
        self.assertIn("bind mount", meta["owner_evidence"])

    def test_init_pid_zero_of_a_stopped_container_is_not_read_with_sudo(self):
        meta = self.init_loginuid_hidden(("1001\n", 0), init_pid=0)
        self.assertEqual(meta["owner_user"], "bob")

    def test_exited_pid_proc_file_is_not_read_with_sudo(self):
        ran = []
        self.host({}, {})
        with mock.patch.object(gc, "_run", lambda cmd, timeout=10.0: (ran.append(cmd), ("", 1))[1]):
            self.assertIsNone(gc._pid_file(900, "loginuid"))
        self.assertEqual(ran, [])

    def test_container_init_loginuid_used_when_the_gpu_process_has_none(self):
        files = _proc_files(4242, cgroup=CONTAINER_ID, loginuid=4294967295)
        files["/proc/900/loginuid"] = "1002\n"
        commands = {"docker ps": (self.container_line("shared"), 0),
                    "docker inspect": (self.inspect_json("shared", mounts=["/home/alice/data"], init_pid=900), 0)}
        line, _, containers = self.who_line(4242, files, commands)
        self.assertIn(": bob [container shared", line)
        self.assertEqual(containers[CONTAINER_ID[:12]]["owner_evidence"], "loginuid of the container init process")

    def test_live_docker_exec_user_used_before_mount_and_name(self):
        files = _proc_files(4242, cgroup=CONTAINER_ID)
        commands = {"docker ps": (self.container_line("bob-box"), 0),
                    "docker inspect": (self.inspect_json("bob-box", mounts=["/home/bob/x"]), 0),
                    "pgrep": ("5555 docker exec -it bob-box bash\n", 0), "ps -o user=": ("alice\n", 0)}
        line, _, containers = self.who_line(4242, files, commands)
        self.assertIn(": alice [container bob-box", line)
        self.assertIn("docker exec", containers[CONTAINER_ID[:12]]["owner_evidence"])

    def test_owner_label_used_before_mount(self):
        files = _proc_files(4242, cgroup=CONTAINER_ID)
        commands = {"docker ps": (self.container_line("c"), 0),
                    "docker inspect": (self.inspect_json("c", mounts=["/home/bob/x"], labels={"owner": "alice"}), 0)}
        line, _, _ = self.who_line(4242, files, commands)
        self.assertIn(": alice [container c", line)

    def test_mount_owner_is_only_the_fallback_without_direct_evidence(self):
        files = _proc_files(4242, cgroup=CONTAINER_ID)
        commands = {"docker ps": (self.container_line("c"), 0),
                    "docker inspect": (self.inspect_json("c", mounts=["/home/bob/x"]), 0), "stat -c": ("bob\n", 0)}
        line, _, containers = self.who_line(4242, files, commands)
        self.assertIn(": bob [container c", line)
        self.assertIn("bind mount", containers[CONTAINER_ID[:12]]["owner_evidence"])

    def test_docker_unavailable_still_names_the_loginuid_person(self):
        files = _proc_files(4242, cgroup=CONTAINER_ID, loginuid=1001)
        line, pinfo, _ = self.who_line(4242, files, {})
        self.assertIn(": alice [pid 4242", line)
        self.assertEqual(pinfo["owner_evidence"], "process loginuid")

    def test_host_root_process_uses_its_loginuid(self):
        line, _, _ = self.who_line(4242, _proc_files(4242, loginuid=1002), {})
        self.assertIn(": bob [pid 4242", line)

    def test_container_uid_is_not_a_host_login(self):
        # uid 1002 inside alice's container is not bob on the host: only the loginuid names the person.
        files = _proc_files(4242, uid=1002, cgroup=CONTAINER_ID, loginuid=1001)
        commands = {"docker ps": (self.container_line("alice-dev"), 0), "docker inspect": (self.inspect_json("alice-dev"), 0)}
        line, _, _ = self.who_line(4242, files, commands)
        self.assertIn(": alice [container alice-dev", line)

    def test_several_nearby_logins_give_an_error_not_an_or_list(self):
        journal = "session opened for user alice(uid=1001)\nsession opened for user bob(uid=1002)\n"
        commands = {"journalctl": (journal, 0), "who": ("alice pts/0\nbob pts/1\n", 0)}
        line, pinfo, _ = self.who_line(4242, _proc_files(4242), commands)
        self.assertIsNone(pinfo["owner_user"])
        self.assertIn("could not determine the owner", line)
        self.assertNotIn(" or ", line)

    def test_only_the_surviving_session_is_the_owner(self):
        journal = "session opened for user alice(uid=1001)\nsession opened for user bob(uid=1002)\n"
        commands = {"journalctl": (journal, 0), "who": ("bob pts/1\n", 0)}
        line, pinfo, _ = self.who_line(4242, _proc_files(4242), commands)
        self.assertEqual(pinfo["owner_user"], "bob")

    def test_exited_pid_is_resolved_from_the_journal_by_pid(self):
        commands = {"journalctl": (json.dumps({"_AUDIT_LOGINUID": "1001", "_PID": "4242"}) + "\n", 0)}
        line, pinfo, _ = self.who_line(4242, {}, commands)
        self.assertEqual(pinfo["owner_user"], "alice")
        self.assertIn("journal", pinfo["owner_evidence"])

    def test_hidepid_proc_files_are_read_with_sudo(self):
        self.host({}, {"cat /proc/4242/stat": (_proc_files(4242)["/proc/4242/stat"], 0)})
        with mock.patch.object(gc.os.path, "isdir", lambda path: path.endswith("/proc/4242")):
            self.assertEqual(gc._parse_stat(4242)["starttime_ticks"], 1000)

    def test_container_name_prefix_is_not_a_login(self):
        occ = {"docker_id": "abc", "container": "mi450_c", "user": "root"}
        containers = {"abc": {"owner_user": None, "owner_error": "no login account found for container mi450_c"}}
        owner, _ = gu._infer_owner_contact(occ, containers)
        self.assertNotIn("mi450 ", owner + " ")
        self.assertIn("could not determine the owner", owner)


class TestFdTargetsBatched(unittest.TestCase):
    """A foreign process with many fds must cost one sudo call, not one per fd."""

    def test_unreadable_process_uses_one_sudo_ls_call(self):
        listing = (
            "total 0\n"
            "lrwx------ 1 u g 64 Nov  4 20:00 0 -> /dev/null\n"
            "lrwx------ 1 u g 64 Nov  4 20:00 3 -> /tmp/foo.lock\n"
            "lrwx------ 1 u g 64 Nov  4 20:00 4 -> /dev/kfd\n"
        )
        calls = []

        def fake_run(cmd, timeout=10.0):
            calls.append(cmd)
            return listing, 0

        def deny(_path):
            raise PermissionError

        orig_run, orig_listdir = gc._run, gc.os.listdir
        gc._run, gc.os.listdir = fake_run, deny
        try:
            self.assertEqual(gc._find_lock_fds(4242), ["/tmp/foo.lock"])
        finally:
            gc._run, gc.os.listdir = orig_run, orig_listdir
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:3], ["sudo", "-n", "ls"])


class TestSudoBudget(unittest.TestCase):
    """Privileged lookups share one wall-clock budget per collect()."""

    def test_spent_budget_skips_sudo_without_running_it(self):
        ran = []
        orig_run, orig_deadline = gc._run, gc._sudo_deadline
        gc._run = lambda cmd, timeout=10.0: (ran.append(cmd), ("x", 0))[1]
        try:
            gc._start_sudo_budget()
            gc._sudo_deadline = gc.time.monotonic() - 1.0
            self.assertEqual(gc._run_sudo(["sudo", "-n", "true"]), ("", -1))
            self.assertEqual(ran, [])
            self.assertTrue(gc._sudo_budget_spent)
        finally:
            gc._run, gc._sudo_deadline = orig_run, orig_deadline
            gc._sudo_budget_spent = False

    def test_open_budget_runs_sudo_with_capped_timeout(self):
        seen = []
        orig_run, orig_deadline = gc._run, gc._sudo_deadline
        gc._run = lambda cmd, timeout=10.0: (seen.append(timeout), ("ok", 0))[1]
        try:
            gc._start_sudo_budget()
            self.assertEqual(gc._run_sudo(["sudo", "-n", "true"], timeout=60.0), ("ok", 0))
            self.assertLessEqual(seen[0], gc._SUDO_BUDGET_S)
        finally:
            gc._run, gc._sudo_deadline = orig_run, orig_deadline


if __name__ == "__main__":
    unittest.main()
