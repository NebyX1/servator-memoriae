"""Los respaldos usan los volúmenes reales y no restauran sobre servicios activos."""
import sys
import pytest
from scripts import backup, restore


def test_backup_uses_compose_volume_names(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(sys, 'argv', ['backup.py', '--volumes-only', '--out', str(tmp_path)])
    monkeypatch.setattr(backup, 'compose_volumes', lambda: {'servator-data': 'proyecto_servator-data', 'model-cache': 'proyecto_model-cache'})
    monkeypatch.setattr(backup, 'running_services', lambda: set())
    monkeypatch.setattr(backup, 'volume_exists', lambda name: True)
    monkeypatch.setattr(backup, 'run', lambda cmd, **kwargs: commands.append(cmd))
    backup.main()
    mounts = [arg for command in commands for arg in command if ':/src:ro' in arg]
    assert set(mounts) == {'proyecto_servator-data:/src:ro', 'proyecto_model-cache:/src:ro'}


def test_restore_checks_services_before_writing(tmp_path, monkeypatch):
    (tmp_path / 'servator-data.tar.gz').write_bytes(b'archivo de prueba')
    commands = []
    monkeypatch.setattr(sys, 'argv', ['restore.py', '--src', str(tmp_path), '--volumes-only', '--yes'])
    monkeypatch.setattr(restore, 'compose_volumes', lambda: {'servator-data': 'proyecto_servator-data'})
    monkeypatch.setattr(restore, 'volume_exists', lambda name: True)
    monkeypatch.setattr(restore, 'running_services', lambda: {'backend', 'postgres'})
    monkeypatch.setattr(restore, 'run', lambda cmd, **kwargs: commands.append(cmd))
    with pytest.raises(SystemExit, match='Detené backend'):
        restore.main()
    assert commands == []
    monkeypatch.setattr(restore, 'running_services', lambda: {'postgres'})
    restore.main()
    assert 'proyecto_servator-data:/dst' in commands[0]


def test_restore_validates_all_archives_before_writing(tmp_path, monkeypatch):
    (tmp_path / 'servator-data.tar.gz').write_bytes(b'prueba')
    (tmp_path / 'zz-no-reconocido.tar.gz').write_bytes(b'prueba')
    commands = []
    monkeypatch.setattr(sys, 'argv', ['restore.py', '--src', str(tmp_path), '--volumes-only', '--yes'])
    monkeypatch.setattr(restore, 'compose_volumes', lambda: {'servator-data': 'proyecto_servator-data'})
    monkeypatch.setattr(restore, 'volume_exists', lambda name: True)
    monkeypatch.setattr(restore, 'run', lambda cmd, **kwargs: commands.append(cmd))
    with pytest.raises(SystemExit, match='no reconocido'):
        restore.main()
    assert commands == []
