"""Strict desktop tool registry. No model code or shell is executed here."""
from dataclasses import dataclass
from pathlib import Path
import configparser
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from diagnostics import timing
import threading
import time
from urllib.parse import urlencode
from application_resolver import resolve_applications
from smart_permissions import private_component

# Exact schemas are also enforced in validate_call(), not just shown to the model.
PARAMETERS = {
    'list_applications': {}, 'system_info': {},
    'open_application': {'application': (str, 240)},
    'open_directory': {'directory': (str,4096)},
    'search_files': {'directory': (str, 4096), 'name': (str, 200)},
    'web_search': {'query': (str, 1000)},
    'draft_bash': {'script': (str, 16000)},
}
DESCRIPTIONS = {
    'list_applications': 'List installed applications and friendly names. Ordinary users do not need desktop identifiers.',
    'system_info': 'Read basic Linux OS, CPU, memory, root disk usage and uptime.',
    'open_application': 'Open an installed application using its ordinary name or purpose, e.g. calculator, file manager, terminal, KCalc, or Dolphin. Resolve locally; ask the user to choose if ambiguous. Never ask the user for desktop IDs or executable paths. Ordinary trusted graphical apps may launch automatically; the application enforces permission policy.',
    'open_directory': 'Open an existing directory in the default file manager, using an absolute path, ~/ path, or Home/Downloads/Documents/Desktop/Pictures/Music/Videos. Ordinary user directories open automatically; private or external locations require permission.',
    'search_files': 'Search filenames within a directory; previously authorized locations need no repeat prompt. New/private scopes require authorization. No contents or symlinks are read.',
    'web_search': 'Request opening a DuckDuckGo search in the default browser. User confirmation is mandatory; query leaves this device.',
    'draft_bash': 'Return Bash text for copying only. Never execute or save this script.',
}
PROTECTED = {'open_application', 'open_directory', 'search_files', 'web_search'}


def schemas():
    return [{'type': 'function', 'function': {'name': name, 'description': DESCRIPTIONS[name],
        'parameters': {'type': 'object', 'properties': {key: {'type': 'string', 'maxLength': rule[1]}
         for key, rule in params.items()}, 'required': list(params), 'additionalProperties': False}}}
        for name, params in PARAMETERS.items()]


def validate_call(call):
    if not isinstance(call, dict) or set(call) != {'name', 'arguments'}:
        raise ValueError('Expected an exact tool name and arguments object.')
    name, args = call['name'], call['arguments']
    if not isinstance(name, str) or name not in PARAMETERS:
        raise ValueError('Unknown desktop tool.')
    params=PARAMETERS[name]
    if name=='open_application' and isinstance(args,dict) and set(args)=={'desktop_id'}:
        params={'desktop_id':(str,240)}  # Internal canonical form; keep older integrations compatible.
    if not isinstance(args, dict) or set(args) != set(params):
        raise ValueError('Unexpected or missing tool arguments.')
    for key, (kind, limit) in params.items():
        value = args[key]
        if type(value) is not kind or not value.strip() or len(value) > limit or '\x00' in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError('Invalid argument: ' + key)
        if key != 'script' and any(ord(char) < 32 for char in value):
            raise ValueError('Control characters are not allowed: ' + key)
    if name == 'open_application' and 'desktop_id' in args and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,230}\.desktop', args['desktop_id']):
        raise ValueError('Invalid application reference. Request an application by its ordinary name, not a command or executable path.')
    if name=='open_directory':
        from PySide6.QtCore import QStandardPaths
        locations={'home':QStandardPaths.HomeLocation,'downloads':QStandardPaths.DownloadLocation,
            'documents':QStandardPaths.DocumentsLocation,'desktop':QStandardPaths.DesktopLocation,
            'pictures':QStandardPaths.PicturesLocation,'music':QStandardPaths.MusicLocation,'videos':QStandardPaths.MoviesLocation}
        aliases={key:Path(QStandardPaths.writableLocation(location)) for key,location in locations.items()}
        raw=args['directory']
        args=dict(args)
        args['directory']=str(aliases.get(raw.strip().casefold(), Path(raw).expanduser() if raw=='~' or raw.startswith('~/') else Path(raw)))
    if name in ('search_files','open_directory') and not Path(args['directory']).is_absolute():
        raise ValueError('Search directory must be an absolute path.')
    return {'name': name, 'arguments': dict(args)}


def action_key(call):
    return json.dumps(call, sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class Grant:
    """Created by the permission broker, never accepted in model arguments."""
    key: str
    mode: str = "confirmed"


class Cancelled(Exception):
    pass


def check_cancel(event):
    if event.is_set():
        raise Cancelled('Desktop action cancelled.')


def application_catalog():
    roots = [Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))]
    roots += [Path(p) for p in os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':') if p]
    result, seen = {}, set()
    for root in roots:
        folder = root/'applications'
        if not folder.is_dir():
            continue
        for base, dirs, files in os.walk(folder, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not (Path(base)/d).is_symlink())
            for filename in sorted(files):
                if not filename.endswith('.desktop'):
                    continue
                path = Path(base)/filename
                identifier = str(path.relative_to(folder)).replace(os.sep, '-')
                if identifier in seen:
                    continue
                seen.add(identifier)  # Hidden user overrides must mask system entries.
                try:
                    if path.is_symlink() or path.stat().st_size > 65536:
                        continue
                    data = path.read_bytes()
                    config = configparser.ConfigParser(interpolation=None, strict=False)
                    config.read_string(data.decode('utf-8'))
                    entry = config['Desktop Entry']
                    if entry.get('Type') != 'Application' or entry.getboolean('Hidden', False) or entry.getboolean('NoDisplay', False):
                        continue
                    if entry.getboolean('Terminal', False) or not (entry.get('Exec') or entry.getboolean('DBusActivatable', False)):
                        continue
                    if entry.get('TryExec') and not shutil.which(entry['TryExec']):
                        continue
                    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,230}\.desktop',identifier):
                        continue
                    result[identifier] = {'name': entry.get('Name',identifier)[:200],
                        'path': str(path.absolute()), 'digest': hashlib.sha256(data).hexdigest(),
                        'names': [value[:200] for key,value in entry.items() if key=='name' or key.startswith('name[')],
                        'generic_names': [value[:200] for key,value in entry.items() if key=='genericname' or key.startswith('genericname[')],
                        'keywords': [word[:100] for key,value in entry.items() if key=='keywords' or key.startswith('keywords[') for word in value.split(';') if word],
                        'categories': entry.get('Categories','').split(';'),
                        'exec': entry.get('Exec',''), 'terminal':entry.getboolean('Terminal',False),
                        'privileged':entry.getboolean('X-KDE-SubstituteUID',False) or bool(entry.get('X-KDE-Username',''))}
                except (OSError, ValueError, KeyError, configparser.Error):
                    continue
    return result


def prepare(call):
    call = validate_call(call)
    details = {'action': call['name'], 'arguments': call['arguments']}
    if call['name'] == 'open_application':
        catalog=application_catalog()
        arguments=call['arguments']
        if 'application' in arguments:
            query=arguments['application']
            matches=resolve_applications(query,catalog)
            if not matches:
                raise ValueError(f'No installed application matches "{query}". Try another friendly name or install the application yourself.')
            if len(matches)!=1 or matches[0]['score']<85:
                details.update(requested_application=query,choices=matches[:6],
                    more_matches=len(matches)>6,
                    notice='Choose an installed application by name. With automatic launching enabled, ordinary graphical apps launch after selection; other apps still require confirmation.')
                return call,details
            identifier=matches[0]['desktop_id']
            details['requested_application']=query
        else:
            identifier=arguments['desktop_id']
        entry=catalog.get(identifier)
        if entry is None:
            raise ValueError('This application is not installed. Try its friendly application name.')
        call={'name':'open_application','arguments':{'desktop_id':identifier}}
        details['arguments']=call['arguments']
        details['application']=entry
    elif call['name'] in ('search_files','open_directory'):
        root = Path(call['arguments']['directory']).resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Search authorization must name a directory.')
        call['arguments']['directory'] = str(root)
        details['arguments'] = call['arguments']
        info = root.stat()
        details['directory_identity'] = [info.st_dev, info.st_ino]
        details['notice'] = ('Authorize filename searches in this directory and ordinary descendants for future requests. Hidden/private subdirectories require separate authorization; no file contents are read.' if call['name']=='search_files' else 'Open this directory in the default file manager? This does not authorize searches or file-content access.')
    elif call['name'] == 'web_search':
        details['url'] = 'https://duckduckgo.com/?' + urlencode({'q': call['arguments']['query']})
        details['notice'] = 'Opens the default browser. This query is sent to the external search provider.'
    return call, details


def launch_gio(arguments, event):
    check_cancel(event)
    executable = shutil.which('gio')
    if not executable:
        raise RuntimeError('GIO launcher is unavailable. Install the distribution GLib tools package.')
    # GUI descendants can inherit stderr. Never wait for pipe EOF/GUI exit.
    started = time.monotonic()
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([executable, *arguments], shell=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors,
            start_new_session=True)
        deadline = time.monotonic()+10
        try:
            while True:
                if event.is_set():
                    raise Cancelled('Launch request cancelled; an already started application cannot be undone.')
                try:
                    code = process.wait(timeout=.1)
                    if code:
                        errors.seek(0)
                        raise RuntimeError('Desktop launcher failed: '+errors.read(2000).decode(errors='replace'))
                    return {'status':'launch_requested', 'note':'Desktop launch request accepted; window appearance is not verified.'}
                except subprocess.TimeoutExpired:
                    if time.monotonic() > deadline:
                        raise RuntimeError('Desktop launcher did not acknowledge the request; window appearance is unknown. See Action Log.')
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            timing('launcher_request', started)


def filename_search(root, needle, event, identity):
    """Descriptor-relative traversal prevents symlink replacement escaping root."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(root, flags)
    try:
        stat = os.fstat(fd)
        if [stat.st_dev, stat.st_ino] != identity:
            raise ValueError('Authorized directory changed; request authorization again.')
        matches, visited, deadline = [], [0], time.monotonic()+6
        limited = [False]
        def walk(current, relative, depth):
            with os.scandir(current) as entries:
                for entry in entries:
                    check_cancel(event)
                    visited[0] += 1
                    if visited[0] > 30000 or len(matches) >= 100 or time.monotonic() > deadline:
                        limited[0] = True
                        return
                    try:
                        if entry.is_symlink():
                            continue
                        path = relative/entry.name
                        if entry.is_file(follow_symlinks=False) and needle.casefold() in entry.name.casefold():
                            matches.append(str(Path(root)/path))
                        if entry.is_dir(follow_symlinks=False):
                            if private_component(entry.name):
                                continue
                            if depth >= 24:
                                limited[0] = True
                                continue
                            child = os.open(entry.name, flags, dir_fd=current)
                            try:
                                walk(child, path, depth+1)
                            finally:
                                os.close(child)
                            if limited[0] and (len(matches)>=100 or visited[0]>30000 or time.monotonic()>deadline):
                                return
                    except OSError:
                        continue
        walk(fd, Path(), 0)
        return {'directory': root, 'matches': matches, 'truncated': limited[0], 'filenames_only': True}
    finally:
        os.close(fd)


def execute(call, details, event, grant=None):
    call = validate_call(call)
    name, args = call['name'], call['arguments']
    check_cancel(event)
    if name in PROTECTED and (not isinstance(grant, Grant) or grant.key != action_key(call)):
        raise PermissionError('Explicit permission for these exact arguments is required.')
    if name == 'open_application':
        if 'desktop_id' not in args:
            raise ValueError('Application name must be resolved and confirmed before launch.')
        entry = application_catalog().get(args['desktop_id'])
        if entry != details.get('application'):
            raise ValueError('Application entry changed since confirmation; request again.')
        result=launch_gio(['launch', entry['path']], event)
        return {**result,'application':entry['name']}
    if name == 'open_directory':
        root=Path(args['directory'])
        info=root.stat()
        if root.is_symlink() or [info.st_dev,info.st_ino]!=details['directory_identity']:
            raise ValueError('Directory changed; request again.')
        result=launch_gio(['open',root.as_uri()],event)
        return {**result,'directory':str(root)}
    if name == 'web_search':
        url = 'https://duckduckgo.com/?' + urlencode({'q': args['query']})
        return launch_gio(['open', url], event)
    if name == 'search_files':
        return filename_search(args['directory'], args['name'], event, details['directory_identity'])
    if name == 'draft_bash':
        return {'script': args['script'], 'executed': False, 'note': 'Copyable text only; Hya did not run or save this script.'}
    if name == 'list_applications':
        entries = application_catalog()
        return {'applications': [{'desktop_id': k, 'name': v['name']} for k,v in sorted(entries.items())[:250]], 'truncated': len(entries)>250}
    if name == 'system_info':
        memory = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, value = line.split(':',1)
            if key in ('MemTotal','MemAvailable'): memory[key+'_kib'] = int(value.split()[0])
        disk = shutil.disk_usage('/')
        try: os_name = platform.freedesktop_os_release().get('PRETTY_NAME',platform.system())
        except OSError: os_name = platform.system()
        cpu = platform.processor()
        for line in Path('/proc/cpuinfo').read_text()[:262144].splitlines():
            if line.startswith('model name'):
                cpu = line.split(':',1)[1].strip()
                break
        return {'os': os_name, 'cpu': cpu, 'logical_cpus': os.cpu_count(), 'memory': memory,
                'root_disk_bytes': {'total': disk.total, 'used': disk.used, 'free': disk.free},
                'uptime_seconds': float(Path('/proc/uptime').read_text().split()[0])}
    raise ValueError('Unknown tool.')
