from pathlib import Path
import json

DEFAULT_RULES = {
    # Lower priority number wins. Filename rules can therefore override broad extension rules.
    'Assignment Files': {
        'extensions': [],
        'filename_contains': ['assignment', 'assgmt', 'task', 'homework', 'practical', 'lab'],
        'priority': 1,
        'destination': 'Assignments',
    },
    'Report Files': {
        'extensions': [],
        'filename_contains': ['report', 'summary', 'analysis'],
        'priority': 2,
        'destination': 'Reports',
    },
    'Project Files': {
        'extensions': [],
        'filename_contains': ['project', 'proj'],
        'priority': 3,
        'destination': 'Projects',
    },
    'Documents': {
        'extensions': ['.pdf','.doc','.docx','.txt','.rtf','.odt','.xls','.xlsx','.ppt','.pptx','.csv'],
        'filename_contains': [], 'priority': 100, 'destination': 'Documents',
    },
    'Images': {
        'extensions': ['.jpg','.jpeg','.png','.gif','.webp','.bmp','.tiff','.svg'],
        'filename_contains': [], 'priority': 100, 'destination': 'Images',
    },
    'Videos': {
        'extensions': ['.mp4','.mkv','.avi','.mov','.webm','.flv','.wmv'],
        'filename_contains': [], 'priority': 100, 'destination': 'Videos',
    },
    'Audio': {
        'extensions': ['.mp3','.wav','.flac','.aac','.ogg','.m4a','.opus'],
        'filename_contains': [], 'priority': 100, 'destination': 'Audio',
    },
    'Archives': {
        'extensions': ['.zip','.7z','.rar','.tar','.gz','.bz2','.xz'],
        'filename_contains': [], 'priority': 100, 'destination': 'Archives',
    },
    'Code': {
        'extensions': ['.py','.js','.ts','.jsx','.tsx','.java','.c','.cpp','.h','.hpp','.cs','.go','.rs','.html','.css','.json','.xml','.sql','.sh'],
        'filename_contains': [], 'priority': 100, 'destination': 'Code',
    },
    'Installers': {
        'extensions': ['.exe','.msi','.deb','.rpm','.pkg','.dmg','.appimage','.iso'],
        'filename_contains': [], 'priority': 100, 'destination': 'Installers',
    },
}

class RuleStore:
    def __init__(self, path=None):
        self.path = Path(path or Path.home() / '.fileflow' / 'rules.json')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rules = self.load()

    def load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                normalized = {}
                for i, (name, value) in enumerate(data.items()):
                    if isinstance(value, dict):
                        normalized[name] = {
                            'extensions': value.get('extensions', []),
                            'filename_contains': value.get('filename_contains', []),
                            'priority': int(value.get('priority', i + 1)),
                            'destination': value.get('destination') or name,
                        }
                    else:
                        normalized[name] = {
                            'extensions': value,
                            'filename_contains': [],
                            'priority': i + 1,
                            'destination': name,
                        }
                # Preserve existing user rules, but add newly available smart defaults.
                for name, rule in DEFAULT_RULES.items():
                    if name not in normalized:
                        normalized[name] = json.loads(json.dumps(rule))
                return normalized
            except Exception:
                pass
        return json.loads(json.dumps(DEFAULT_RULES))

    def ordered(self):
        return sorted(self.rules.items(), key=lambda item: (int(item[1].get('priority', 100)), item[0].lower()))

    def save(self):
        self.path.write_text(json.dumps(self.rules, indent=2))
