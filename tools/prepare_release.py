"""Deterministic source snapshot + checksummed PKGBUILD in an isolated directory."""
import argparse
import gzip
import hashlib
import io
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.9.2'
EPOCH=1792368000


def source_files(root=ROOT):
    files=list(root.glob('*.py'))+list(root.glob('*.md'))+[root/'docs/history/README-v0.9.1.txt',root/'LICENSE',root/'peek.qml',root/'system_prompt.txt']
    files += list((root/'tests').glob('*.py'))
    files += list((root/'tests/fixtures').glob('*.py'))
    files += [root/'assets/hya.svg',root/'packaging/hya',root/'packaging/io.hyalos.Hya.desktop',
              root/'packaging/PKGBUILD.in',root/'packaging/LICENSE.notice',root/'tools/prepare_release.py']
    files += list((root/'native').glob('*.cpp'))+[root/'native/CMakeLists.txt']
    return sorted(set(files),key=lambda p:p.relative_to(root).as_posix())


def prepare(output,root=ROOT):
    output=Path(output).resolve()
    if output==root or root in output.parents:raise ValueError('Release work must be outside the editable project.')
    output.mkdir(parents=True,exist_ok=True)
    destination=output/f'hya-{VERSION}.tar.gz'
    with destination.open('wb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=EPOCH) as zipped,tarfile.open(fileobj=zipped,mode='w',format=tarfile.GNU_FORMAT) as archive:
        for path in source_files(root):
            if not path.is_file() or path.is_symlink():raise ValueError('Missing or symlinked release input: '+str(path))
            data=path.read_bytes()
            info=tarfile.TarInfo(f'hya-{VERSION}/'+path.relative_to(root).as_posix())
            info.size=len(data);info.mode=0o755 if path==root/'packaging/hya' else 0o644
            info.mtime=EPOCH;info.uid=info.gid=0;info.uname=info.gname='root'
            archive.addfile(info,io.BytesIO(data))
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    template=(root/'packaging/PKGBUILD.in').read_text()
    (output/'PKGBUILD').write_text(template.replace('@SOURCE_SHA256@',digest))
    (output/'SOURCE_DATE_EPOCH').write_text(str(EPOCH)+'\n')
    return destination,digest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    source,digest=prepare(args.output)
    print(source);print('sha256:',digest)
