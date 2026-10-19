"""Human-facing action presentation; structured results remain internal."""
import json
import re


def action_summary(tool, result):
    if not isinstance(result, dict):
        return 'The desktop action returned an invalid result. See Action Log.'
    if 'error' in result:
        error = str(result['error']).casefold()
        if 'denied' in error: return 'Permission was denied; no new action was requested.'
        if 'cancel' in error: return 'The desktop action was cancelled.'
        if 'no installed' in error or 'no matching' in error: return 'No matching installed application was found.'
        return 'The desktop action could not be completed. See Action Log for details.'
    if 'script' in result:
        script = str(result['script'])
        fence = '`' * (max([3] + [len(x) for x in re.findall(r'`+', script)]) + 1)
        return 'Bash draft — copy only; not executed:\n' + fence + 'bash\n' + script + '\n' + fence
    if result.get('status') == 'launch_requested':
        target = result.get('application') or result.get('directory')
        return ('Launch requested for ' + str(target) + '.' if target else 'Launch requested.') + ' Window appearance is not verified.'
    if tool == 'system_info':
        memory = result.get('memory', {})
        disk = result.get('root_disk_bytes', {})
        gib = lambda n: f'{n / 1024**3:.1f} GiB'
        return (f"{result.get('os', 'Linux')}\nCPU: {result.get('cpu', 'Unknown')} ({result.get('logical_cpus', '?')} logical CPUs)\n"
                f"RAM: {gib(memory.get('MemAvailable_kib', 0)*1024)} available / {gib(memory.get('MemTotal_kib', 0)*1024)}\n"
                f"Disk: {gib(disk.get('free', 0))} free / {gib(disk.get('total', 0))}\n"
                f"Uptime: {result.get('uptime_seconds', 0)/3600:.1f} hours")
    if 'matches' in result:
        matches = result['matches']
        return 'Filename search results:\n' + '\n'.join(map(str, matches)) if matches else 'No matching filenames found.'
    if 'applications' in result:
        return 'Installed applications:\n' + '\n'.join(str(x.get('name', '')) for x in result['applications'])
    return 'Desktop action completed. See Action Log for details.'


def visible_text(text, tool=''):
    """Recognize legacy debug bubbles and whole tool-shaped JSON, not user code."""
    original = text
    if text.startswith('Desktop tool · '):
        header, _, text = text.partition('\n')
        tool = header.removeprefix('Desktop tool · ').strip()
    candidate = text.strip()
    if candidate.startswith('```json') and candidate.endswith('```'):
        candidate = candidate[7:-3].strip()
    try:
        value = json.loads(candidate)
    except (ValueError, TypeError):
        if original.startswith('Desktop tool · '):
            return 'Desktop action details are available in Action Log.'
        if tool:
            decoder = json.JSONDecoder()
            pieces, position = [], 0
            for match in re.finditer(r'\{', text):
                if match.start() < position: continue
                try: value, end = decoder.raw_decode(text[match.start():])
                except ValueError: continue
                if isinstance(value, dict) and set(value) & {'error','status','executed','root_disk_bytes'}:
                    pieces.extend((text[position:match.start()], action_summary(tool,value)))
                    position = match.start()+end
            if pieces: return ''.join(pieces)+text[position:]
            if any(key in text for key in ('"error"','"status"','Desktop tool · ')):
                return 'Desktop action details are available in Action Log.'
        return original
    if isinstance(value, dict) and (tool or set(value) & {'error', 'status', 'executed', 'root_disk_bytes'}):
        return action_summary(tool, value)
    return original


def stream_text(text, tool=''):
    stripped = text.lstrip()
    if tool and stripped.startswith(('{', '```json')):
        candidate = stripped[7:-3].strip() if stripped.startswith('```json') and stripped.endswith('```') else stripped
        try: json.loads(candidate)
        except ValueError: return 'Preparing action summary…'
    return visible_text(text, tool)
