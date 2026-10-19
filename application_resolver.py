"""Name matching against discovered entries only; aliases never create an app."""
import re
import unicodedata

GROUPS = {
    'calculator': {'calculator','calc','kcalc','gnome calculator','qalculate','qalculate gtk','speedcrunch','galculator','mate calc'},
    'file manager': {'file manager','file browser','file explorer','files','dolphin','nautilus','thunar','nemo','pcmanfm','caja'},
    'terminal': {'terminal','terminal emulator','console','konsole','gnome terminal','xfce4 terminal','xterm','kitty','alacritty','wezterm','foot'},
}
CATEGORIES = {'calculator':'Calculator','file manager':'FileManager','terminal':'TerminalEmulator'}
GENERIC = {'calculator','calc','file manager','file browser','file explorer','files','terminal','terminal emulator','console'}


def normalize(text):
    return ' '.join(re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',text).casefold()))


def query_name(text):
    text=normalize(text)
    text=re.sub(r'^(?:(?:please|can you|could you) )?(?:open|launch|start|run) (?:the |a |an )?', '', text)
    text=re.sub(r' (?:app|application)(?: please)?$| please$', '', text)
    return text


def resolve_applications(query, catalog):
    key=query_name(query)
    if not key: return []
    group=next((name for name,aliases in GROUPS.items() if key in aliases),None)
    matches=[]
    for identifier,entry in catalog.items():
        names={normalize(value) for value in entry.get('names',[entry['name']])}
        names.add(normalize(entry['name']))
        brand=normalize(identifier[:-8].split('.')[-1])
        generics={normalize(value) for value in entry.get('generic_names',[])}
        keywords={normalize(value) for value in entry.get('keywords',[])}
        score=0
        if key==normalize(identifier) or key==brand or key in names: score=100
        if key in generics: score=max(score,90)
        if key in keywords: score=max(score,85)
        if group and key in GENERIC:
            aliases=GROUPS[group]
            branded=bool((names|{brand}|generics)&aliases)
            classified=CATEGORIES[group] in entry.get('categories',[])
            if branded or classified:
                score=max(score,90)
                # Generic requests must not prefer an app literally named
                # "Calculator" over another installed calculator such as KCalc.
                if key in GENERIC: score=90
        if not score and len(key)>=3:
            words=set(key.split())
            if any(words <= set(value.split()) for value in names|generics|{normalize(identifier[:-8])}): score=70
        if score: matches.append({'desktop_id':identifier,'application':entry,'score':score})
    matches.sort(key=lambda row:(-row['score'],row['application']['name'].casefold(),row['desktop_id']))
    strong=[row for row in matches if row['score']>=85]
    exact=[row for row in strong if row['score']==100]
    if len(exact)==1: return exact
    if len(strong)==1: return strong
    return strong or matches
