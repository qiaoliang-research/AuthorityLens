from pilot_dry_run import main


def test_dry_run_cli_requires_explicit_synthetic_mode(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("PILOT_DRY_RUN", raising=False)

    result = main(["--seed", "8", "--output-dir", str(tmp_path)])

    assert result == 2
    assert "Set PILOT_DRY_RUN=true" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_dry_run_cli_writes_labeled_local_files_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PILOT_DRY_RUN", "true")

    result = main(["--seed", "8", "--output-dir", str(tmp_path)])

    assert result == 0
    output = capsys.readouterr().out
    assert "SYNTHETIC DRY RUN — NOT PARTICIPANT DATA" in output
    assert len(list(tmp_path.iterdir())) == 2
