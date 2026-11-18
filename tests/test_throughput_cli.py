"""task 149：`bfsim probe-throughput` CLI——默认 stub 卡组冒烟（零 db 依赖），
--deck-id 走真实装配；distilled 缺 --policy 显式报错。"""

from battlefrontier.cli import main


def test_probe_cli_stub_smoke(tmp_path, monkeypatch, capsys):
    rc = main(["probe-throughput", "--agent", "heuristic",
               "--games", "4", "--workers", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "判定" in out and "产能" in out


def test_probe_cli_distilled_requires_policy(tmp_path, capsys):
    rc = main(["probe-throughput", "--agent", "distilled",
               "--games", "2", "--workers", "1"])
    assert rc == 1
    assert "policy_path" in capsys.readouterr().out

