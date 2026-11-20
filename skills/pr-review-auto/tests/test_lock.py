import datetime
import json
import os

from prreview import cli, config, state

REPO = "o/r"


def lock_file(write_config, **overrides):
    write_config(**overrides)
    return state.pr_dir(config.load(REPO), REPO, 7) / "lock"


def run_lock(capsys, command: str, holder: str) -> dict:
    capsys.readouterr()
    assert cli.main([command, REPO, "7", "--holder", holder]) == 0
    return json.loads(capsys.readouterr().out)


def age(path, **delta) -> None:
    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(**delta)
    path.write_text(json.dumps({"holder": "a", "since": old.isoformat()}))


def test_lock_first_holder_gets_it(write_config, capsys):
    path = lock_file(write_config)
    assert run_lock(capsys, "lock", "a") == {"locked": True}
    assert json.loads(path.read_text())["holder"] == "a"


def test_lock_second_holder_busy(write_config, capsys):
    lock_file(write_config)
    run_lock(capsys, "lock", "a")
    out = run_lock(capsys, "lock", "b")
    assert out["busy"] is True and out["holder"] == "a"
    datetime.datetime.fromisoformat(out["since"])


def test_lock_stale_is_taken_over(write_config, capsys):
    path = lock_file(write_config)
    run_lock(capsys, "lock", "a")
    age(path, hours=4)
    assert run_lock(capsys, "lock", "b") == {"locked": True}
    assert json.loads(path.read_text())["holder"] == "b"


def test_lock_respects_configured_stale_after(write_config, capsys):
    path = lock_file(write_config, lock_stale_after="1m")
    run_lock(capsys, "lock", "a")
    age(path, minutes=2)
    assert run_lock(capsys, "lock", "b") == {"locked": True}


def test_lock_not_yet_stale_stays_busy(write_config, capsys):
    path = lock_file(write_config)
    run_lock(capsys, "lock", "a")
    age(path, hours=2)
    assert run_lock(capsys, "lock", "b")["busy"] is True


def test_lock_unreadable_file_ages_by_mtime(write_config, capsys):
    path = lock_file(write_config)
    path.parent.mkdir(parents=True)
    path.write_text("")  # a holder that died between create and write
    assert run_lock(capsys, "lock", "b")["busy"] is True  # fresh: still busy
    old = datetime.datetime.now().timestamp() - 4 * 3600
    os.utime(path, (old, old))
    assert run_lock(capsys, "lock", "b") == {"locked": True}


def test_unlock_wrong_holder_keeps_lock(write_config, capsys):
    path = lock_file(write_config)
    run_lock(capsys, "lock", "a")
    assert run_lock(capsys, "unlock", "b") == {"unlocked": False}
    assert path.exists()


def test_unlock_right_holder_and_missing(write_config, capsys):
    path = lock_file(write_config)
    run_lock(capsys, "lock", "a")
    assert run_lock(capsys, "unlock", "a") == {"unlocked": True}
    assert not path.exists()
    assert run_lock(capsys, "unlock", "a") == {"unlocked": False}
    assert run_lock(capsys, "lock", "b") == {"locked": True}
