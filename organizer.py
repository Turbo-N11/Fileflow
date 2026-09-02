from pathlib import Path
from datetime import datetime
import hashlib
import shutil
import time

PROTECTED_NAMES = {'/etc', '/usr', '/bin', '/sbin', '/boot', '/System', '/Library'}

class Organizer:
    def __init__(self, root, rules):
        self.root = Path(root).expanduser().resolve()
        self.rules = rules

    def _ordered_rules(self):
        return sorted(self.rules.items(), key=lambda item: (int(item[1].get('priority', 100)), item[0].lower()))

    def category_for(self, path):
        name = path.name.lower()
        suffix = path.suffix.lower()
        # Rules are priority-based. Filename matches are checked before extensions
        # inside the same rule, allowing e.g. assignment.docx -> Assignments.
        for category, rule in self._ordered_rules():
            if not isinstance(rule, dict):
                rule = {'extensions': rule, 'filename_contains': [], 'destination': category}
            for token in rule.get('filename_contains', []):
                if str(token).strip().lower() and str(token).strip().lower() in name:
                    return category
            exts = [str(x).lower() for x in rule.get('extensions', [])]
            if suffix in exts:
                return category
        return None

    def destination_for(self, category):
        rule = self.rules.get(category, {})
        return str(rule.get('destination') or category)

    def scan(self):
        if not self.root.is_dir():
            return []
        items = []
        try:
            paths = sorted(self.root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return []
        for path in paths:
            try:
                if not path.is_file() or path.name.startswith('.') or self.is_excluded(path):
                    continue
                stat = path.stat()
            except OSError:
                continue
            category = self.category_for(path)
            items.append({
                'source': str(path), 'name': path.name, 'category': category,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')
            })
        return items

    def is_excluded(self, path):
        return path.name.lower().endswith(('.part', '.crdownload', '.tmp'))

    def preview(self):
        result = []
        for item in self.scan():
            if not item['category']:
                continue
            folder = self.destination_for(item['category'])
            dest_dir = self.root / folder
            destination = dest_dir / item['name']
            duplicate = destination.exists() and self.hash_file(Path(item['source'])) == self.hash_file(destination)
            result.append({
                **item,
                'destination_folder': folder,
                'destination': str(destination),
                'conflict': destination.exists(),
                'duplicate': duplicate,
            })
        return result

    @staticmethod
    def unique_path(path):
        if not path.exists():
            return path
        stem, suffix = path.stem, path.suffix
        i = 1
        while True:
            candidate = path.with_name(f'{stem} ({i}){suffix}')
            if not candidate.exists():
                return candidate
            i += 1

    @staticmethod
    def hash_file(path, chunk=1024 * 1024):
        try:
            h = hashlib.sha256()
            with path.open('rb') as f:
                while data := f.read(chunk):
                    h.update(data)
            return h.hexdigest()
        except OSError:
            return None

    def execute(self, items, policy='rename'):
        if self.root == Path('/') or any(str(self.root).startswith(p + '/') for p in PROTECTED_NAMES):
            raise PermissionError('Protected system folder cannot be organized.')
        moved, errors = [], []
        for item in items:
            src = Path(item['source'])
            try:
                if not src.exists() or not src.is_file():
                    continue
                folder = item.get('destination_folder') or self.destination_for(item['category'])
                dest_dir = self.root / folder
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / src.name
                if dest.exists():
                    if policy == 'skip':
                        continue
                    if policy == 'replace':
                        if self.hash_file(src) == self.hash_file(dest):
                            errors.append({'source': str(src), 'error': 'Duplicate content already exists'})
                            continue
                        dest.unlink()
                    else:
                        dest = self.unique_path(dest)
                shutil.move(str(src), str(dest))
                moved.append({'source': str(src), 'destination': str(dest), 'size': item.get('size', 0), 'timestamp': datetime.now().isoformat()})
            except (OSError, PermissionError) as exc:
                errors.append({'source': str(src), 'error': str(exc)})
        return {'moved': moved, 'errors': errors}

    def stable(self, path, delay=0.8):
        path = Path(path)
        try:
            first = path.stat().st_size
            time.sleep(delay)
            return path.exists() and path.stat().st_size == first
        except OSError:
            return False
