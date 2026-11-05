"""Vendor Devicon language logos. Run manually; daily rendering stays offline."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
from urllib.request import urlopen
import xml.etree.ElementTree as ET

REVISION = '32fe1d3b3f36ad11f90ab94f7db59738139c2bf6'
BASE = f'https://raw.githubusercontent.com/devicons/devicon/{REVISION}'
DIRECTORY = Path(__file__).resolve().parent
CACHE = DIRECTORY.parents[1] / 'output' / 'devicon-cache' / REVISION
EXTRA_ICONS = set('''
    astro ballerina bash cairo cmake docker elm emacs erlang godot googleappscript
    handlebars json latex less mysql nixos norg openapi opengl oracle postgresql
    powershell processing pug react sass sqlite spss stata stylus svelte terraform
    tex unity unrealengine vim vuejs
'''.split())
# Original dark lettering and line art need more ink contrast on GitHub dark.
DARK_ADJUST = set('''
    aarch64 bash coffeescript emacs erlang fortran haskell idris java less lua
    mysql objectivec opencl processing purescript spss stata stylus systemverilog
    toml unity verilog xml yaml zsh
'''.split())
# WakaTime names and common editor aliases that differ from Devicon's slugs.
ALIASES = {
    'C++': 'cplusplus', 'CPP': 'cplusplus', 'CXX': 'cplusplus',
    'C#': 'csharp', 'CSharp': 'csharp', 'F#': 'fsharp',
    'Objective-C': 'objectivec', 'Objective-C++': 'objectivec',
    'HTML': 'html5', 'HTML+Razor': 'html5', 'CSHTML': 'html5',
    'CSS': 'css3', 'SCSS': 'sass', 'Sass': 'sass',
    'Shell': 'bash', 'Shell Script': 'bash', 'ShellScript': 'bash',
    'Bash': 'bash', 'sh': 'bash', 'Zsh': 'zsh', 'Fish': 'fish',
    'PowerShell': 'powershell', 'ps1': 'powershell',
    'JavaScript': 'javascript', 'JS': 'javascript', 'MJS': 'javascript',
    'TypeScript': 'typescript', 'TS': 'typescript',
    'JSX': 'react', 'TSX': 'react', 'JavaScript React': 'react',
    'TypeScript React': 'react', 'Vue': 'vuejs', 'Vue.js': 'vuejs',
    'Python': 'python', 'Python3': 'python', 'py': 'python',
    'Jupyter Notebook': 'jupyter', 'IPython': 'jupyter',
    'Go': 'go', 'Golang': 'go', 'RScript': 'r', 'RMarkdown': 'r',
    'Visual Basic': 'visualbasic', 'Visual Basic .NET': 'visualbasic',
    'VB.NET': 'visualbasic', 'VBScript': 'visualbasic',
    'Delphi': 'delphi', 'Pascal': 'delphi', 'Object Pascal': 'delphi',
    'Assembly': 'nasm', 'ASM': 'nasm', 'NASM': 'nasm',
    'ARM Assembly': 'aarch64', 'ARM': 'aarch64',
    'WebAssembly': 'wasm', 'WAT': 'wasm',
    'Emacs Lisp': 'emacs', 'Racket': 'racket', 'V': 'vlang',
    'VimL': 'vim', 'Vim script': 'vim', 'GDScript': 'godot',
    'HCL': 'terraform', 'Terraform': 'terraform', 'Nix': 'nixos',
    'TeX': 'tex', 'LaTeX': 'latex', 'CoffeeScript': 'coffeescript',
    'ClojureScript': 'clojurescript', 'SystemVerilog': 'systemverilog',
    'Mathematica': 'wolfram', 'Wolfram Language': 'wolfram',
    'MATLAB': 'matlab', 'APL': 'apl',
    'JSON': 'json', 'JSONC': 'json', 'JSON5': 'json',
    'YAML': 'yaml', 'YML': 'yaml', 'XML': 'xml', 'XSLT': 'xml',
    'Markdown': 'markdown', 'MDX': 'markdown', 'md': 'markdown',
    'Dockerfile': 'docker', 'Docker': 'docker',
    'CMake': 'cmake', 'GLSL': 'opengl',
    'ShaderLab': 'unity', 'UnrealScript': 'unrealengine',
    'Jinja': 'python', 'Jinja2': 'python', 'Twig': 'php', 'Blade': 'php',
    'ERB': 'ruby', 'Ruby HTML': 'ruby', 'Handlebars': 'handlebars',
    'Mustache': 'handlebars', 'Jade': 'pug',
}


def normalize(name):
    return re.sub(r'[\s_.-]+', '', name.casefold())


def download(path):
    cached = CACHE / path
    if cached.is_file():
        return cached.read_text(encoding='utf-8')
    with urlopen(f'{BASE}/{path}', timeout=45) as response:
        source = response.read().decode('utf-8')
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(source, encoding='utf-8')
    return source


def prepare_svg(source):
    """Flatten simple Devicon styles and keep a self-contained SVG fragment."""
    root = ET.fromstring(source)
    rules = {}
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
        if element.tag in ('script', 'foreignObject', 'image'):
            raise ValueError(f'Unsupported icon element: {element.tag}')
        if element.tag == 'style':
            for selectors, declarations in re.findall(r'([^{}]+)\{([^{}]*)\}', element.text or ''):
                attrs = dict(item.strip().split(':', 1) for item in declarations.split(';') if ':' in item)
                for selector in selectors.split(','):
                    selector = selector.strip()
                    if not re.fullmatch(r'\.[\w-]+', selector):
                        raise ValueError(f'Unsupported CSS selector: {selector}')
                    rules[selector[1:]] = {key.strip(): value.strip() for key, value in attrs.items()}
    for parent in root.iter():
        for child in list(parent):
            if child.tag in ('style', 'title', 'desc', 'metadata'):
                parent.remove(child)
        for name in parent.attrib.pop('class', '').split():
            for key, value in rules[name].items():
                parent.set(key, value)
        for declaration in parent.attrib.pop('style', '').split(';'):
            if ':' in declaration:
                key, value = declaration.split(':', 1)
                if not key.strip().startswith('-'):
                    parent.set(key.strip(), value.strip())
        for key, value in list(parent.attrib.items()):
            if key.startswith('on') or 'http:' in value or 'https:' in value or 'data:' in value:
                raise ValueError('Icons must not contain scripts or external resources.')
            if key.startswith('{'):
                del parent.attrib[key]
                parent.set(key.rsplit('}', 1)[-1], value)
        # Some editor exports leave meaningless href attributes on drawn paths.
        if parent.tag not in ('use', 'linearGradient', 'radialGradient', 'textPath'):
            parent.attrib.pop('href', None)
        parent.tail = None
        if parent.text and not parent.text.strip():
            parent.text = None
    for key in ('width', 'height', 'x', 'y', 'version', 'id', 'data-name', 'color'):
        root.attrib.pop(key, None)
    if 'viewBox' not in root.attrib:
        raise ValueError('Icon needs a viewBox.')
    # One-color logos use the theme's ink; black Rust/Bash/etc stay visible in dark mode.
    paints = {element.get(key).lower() for element in root.iter() for key in ('fill', 'stroke') if element.get(key)}
    monochrome = paints <= {'none', 'black', '#000', '#000000', 'currentcolor'}
    if monochrome:
        for element in root.iter():
            element.attrib.pop('color', None)
            for key in ('fill', 'stroke'):
                if element.get(key, '').lower() in ('black', '#000', '#000000'):
                    element.set(key, 'currentColor')
    root.set('fill', root.get('fill', 'currentColor'))
    svg = ET.tostring(root, encoding='unicode')
    ET.fromstring(svg)
    return svg, monochrome


def main():
    entries = json.loads(download('devicon.json'))
    selected = [entry for entry in entries if entry['name'] in EXTRA_ICONS
                or {'language', 'programming'}.intersection(entry['tags'])]

    def icon(entry):
        versions = entry['versions']['svg']
        version = next((v for v in ('original', 'plain', 'line', 'original-wordmark', 'plain-wordmark') if v in versions))
        path = f"icons/{entry['name']}/{entry['name']}-{version}.svg"
        svg, monochrome = prepare_svg(download(path))
        return entry['name'], {'svg': svg, 'color': entry['color'], 'monochrome': monochrome,
                               'dark_adjust': entry['name'] in DARK_ADJUST,
                               'light_adjust': entry['name'] == 'grpc', 'source': path}

    with ThreadPoolExecutor(max_workers=12) as pool:
        icons = dict(pool.map(icon, selected))
    aliases = {}
    for entry in selected:
        for name in (entry['name'], *entry.get('altnames', [])):
            aliases[normalize(name)] = entry['name']
    for name, slug in ALIASES.items():
        if slug not in icons:
            raise ValueError(f'Missing icon for {name}: {slug}')
        aliases[normalize(name)] = slug
    catalog = {'source': 'https://github.com/devicons/devicon', 'revision': REVISION,
               'icons': dict(sorted(icons.items())), 'aliases': dict(sorted(aliases.items()))}
    (DIRECTORY / 'language-icons.json').write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (DIRECTORY / 'LICENSE-devicon.txt').write_text(download('LICENSE'), encoding='utf-8')
    print(f'Vendored {len(icons)} logos with {len(aliases)} language names and aliases.')


if __name__ == '__main__':
    main()
