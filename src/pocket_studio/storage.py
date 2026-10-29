"""Local project registry and host-observed destination bindings. No network IO."""
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .core import contained, new_id, now, project_lock, read, root_at, save


class StorageError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def home_at(value=None):
    root = Path(value or os.environ.get('POCKET_STUDIO_HOME') or
                Path.home() / '.pocket-studio').expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def registry(home):
    path = contained(home, 'registry.json')
    if not path.exists():
        return {'schema_version': 1, 'projects': []}
    import json
    data = json.loads(path.read_text())
    if data.get('schema_version') != 1 or not isinstance(data.get('projects'), list):
        raise ValueError('Unsupported project registry')
    return data


def register(home, root):
    root = root_at(root)
    if root == home:
        raise ValueError('Project directory must differ from managed home')
    # Always acquire home before project when both locks are needed.
    with project_lock(home), project_lock(root):
        index = registry(home)
        data = read(root)
        pid = data['project_id'] if 'project_id' in data else new_id('project')
        if not isinstance(pid, str) or not re.fullmatch(r'project-[a-f0-9]{12}', pid):
            raise ValueError('Invalid project ID')
        for item in index['projects']:
            if item['id'] == pid and item['path'] != str(root):
                raise ValueError('Project ID already registered at another path; no automatic relocation')
            if item['path'] == str(root) and item['id'] != pid:
                raise ValueError('Registered project identity changed')
        if 'project_id' not in data:
            data['project_id'] = pid
            save(contained(root, 'motion.json'), data)
        item = {'id': pid, 'path': str(root), 'title': data['title']}
        index['projects'] = [p for p in index['projects'] if p['id'] != pid] + [item]
        save(contained(home, 'registry.json'), index)
        return item


def projects(home, project_id=None):
    with project_lock(home):
        entries = registry(home)['projects']
        if project_id is not None:
            entries = [p for p in entries if p['id'] == project_id]
            if not entries:
                raise ValueError('Unknown project ID')
        result = []
        for entry in entries:
            item = dict(entry)
            try:
                data = read(root_at(entry['path']))
                item['available'] = data.get('project_id') == entry['id']
            except (ValueError, OSError, KeyError, TypeError):
                item['available'] = False
            result.append(item)
        if project_id is not None:
            if not result[0]['available']:
                raise ValueError('Registered project unavailable or identity changed')
            return result[0]
        return {'projects': result, 'home': str(home)}


ERRORS = {
    'missing_connector': 'Requires setup: host has no exposed connector for this provider.',
    'auth_required': 'Requires setup: authenticate the connector in the host.',
    'account_selection': 'Select a specific connector account and folder.',
    'permission_denied': 'Destination upload permission has not been established.',
    'network_error': 'Host could not check the destination; retry discovery.',
    'stale_observation': 'Refresh host account, folder and upload permission observations.',
    'unsupported_host': 'This host cannot discover or check connector destinations.',
    'uncertain_transfer': 'Transfer outcome is uncertain; reconcile before retrying.',
}
FIELDS = {'schema_version', 'provider', 'status', 'account_id', 'folder_id',
          'host', 'observed_at', 'expires_at', 'can_upload'}


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError()
        return result
    except (ValueError, AttributeError, TypeError):
        raise StorageError('invalid_observation', 'Observation requires timezone-aware timestamps') from None


def validate_observation(receipt):
    # Never echo unknown keys, raw connector output or rejected values.
    if not isinstance(receipt, dict) or set(receipt) - FIELDS:
        raise StorageError('invalid_observation', 'Only documented non-secret observation fields are accepted')
    if type(receipt.get('schema_version')) is not int or receipt['schema_version'] != 1:
        raise StorageError('invalid_observation', 'Unsupported observation schema')
    if receipt.get('provider') not in ('google_drive', 'dropbox'):
        raise StorageError('unsupported_provider', 'Provider is not supported for destination binding')
    status = receipt.get('status')
    if isinstance(status, str) and status in ERRORS:
        raise StorageError(status, ERRORS[status])
    if status != 'ready':
        raise StorageError('invalid_observation', 'Observation status must be ready or a documented setup error')
    for field in ('account_id', 'folder_id', 'host'):
        value = receipt.get(field)
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:@-]{1,200}', value):
            raise StorageError('account_selection', ERRORS['account_selection'])
    if receipt.get('can_upload') is not True:
        raise StorageError('permission_denied', ERRORS['permission_denied'])
    observed, expires = timestamp(receipt.get('observed_at')), timestamp(receipt.get('expires_at'))
    current = datetime.now(timezone.utc)
    if not observed <= current < expires or (expires - observed).total_seconds() > 86400:
        raise StorageError('stale_observation', ERRORS['stale_observation'])
    return dict(receipt)


def bind_destination(root, receipt):
    receipt = validate_observation(receipt)
    with project_lock(root):
        data = read(root)
        old = data.get('destination')
        if old and old['observation'] == receipt:
            return old
        binding = {'id': new_id('destination'), 'observation': receipt,
                   'bound_at': now(), 'evidence': 'host asserted; not independently verified',
                   'transport': 'not_implemented'}
        data['destination'] = binding
        save(contained(root, 'motion.json'), data)
        return binding


def destination_status(root):
    with project_lock(root):
        binding = read(root).get('destination')
        if binding is None:
            return {'bound': False, 'transport': 'not_implemented'}
        try:
            validate_observation(binding['observation'])
            status = 'ready'
        except StorageError as exc:
            status = exc.code
        return {'bound': True, 'status': status, 'binding': binding,
                'upload_available': False}
