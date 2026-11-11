"""Resolve logical volume names using Compose, including project prefixes."""
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def compose_volumes():
    # La salida contiene también variables sensibles: procesarla sin imprimirla.
    output = subprocess.check_output(
        ['docker', 'compose', '--profile', 's3', 'config', '--format', 'json'],
        cwd=ROOT, text=True)
    volumes = json.loads(output).get('volumes', {})
    return {logical: definition['name'] for logical, definition in volumes.items() if definition.get('name')}


def volume_exists(name):
    return subprocess.run(['docker', 'volume', 'inspect', name], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def running_services():
    output = subprocess.check_output(
        ['docker', 'compose', '--profile', 's3', '-f', 'docker-compose.yml', '-f', 'docker-compose.gpu.yml',
         'ps', '--status', 'running', '--services'], cwd=ROOT, text=True)
    return set(output.split())
