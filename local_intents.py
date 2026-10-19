"""Deliberately narrow whole-utterance grammar; never scan prose for commands."""
import re
from application_resolver import resolve_applications

FOLDERS = {'home', 'downloads', 'documents', 'desktop', 'pictures', 'music', 'videos'}


def parse_intent(text):
    if text.strip().casefold() in ('system info', 'system information', 'show system information', 'show system info'):
        return {'name':'system_info', 'arguments':{}}
    # No quotes, negations, punctuation chains, paths, multiline or injected args.
    match = re.fullmatch(r'(?i)(?:please )?(open|launch|show) (?:my |the )?([a-z0-9][a-z0-9 -]{0,70}?)(?: please)?[.!]?', text.strip())
    if not match: return None
    verb, target = match.groups()
    target = target.casefold()
    if set(target.split()) & {'and','or','not','never','without','then','except','but','dont','ignore'}:
        return None
    folder = re.sub(r' folder$| directory$', '', target)
    if folder in FOLDERS:
        return {'name':'open_directory','arguments':{'directory':folder}}
    if verb.casefold() == 'show': return None
    return {'name':'open_application','arguments':{'application':target}}


def resolve_intent(text, catalog):
    call = parse_intent(text)
    if call is None or call['name'] != 'open_application': return call
    matches = resolve_applications(call['arguments']['application'], catalog)
    if len(matches) == 1 and matches[0]['score'] >= 85:
        return {'name':'open_application','arguments':{'desktop_id':matches[0]['desktop_id']}}
    return None
