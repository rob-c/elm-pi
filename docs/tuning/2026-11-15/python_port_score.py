"""Independent artifact and workflow scoring for this Python-port treadmill.

Run with WORK [ARM ...] to rescore completed reports. Model projects are read only;
checks use -B and only the reports directory receives scorer output.
"""
import ast
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

GREETING = "café — 日本語 — αβγ\n"
TODO = "Check café — 日本語\nReview αβγ results"
PARALLEL_CHECK = '''from numbers import clamp
from words import initials
assert [clamp(x, 1, 3) for x in (-2, 1, 2, 3, 7)] == [1, 1, 2, 3, 3]
try:
    clamp(2, 3, 1)
except ValueError:
    pass
else:
    raise AssertionError('reversed bounds accepted')
assert initials('') == ''
assert initials('  ada\\tLovelace  ') == 'AL'
assert clamp(len(initials('Ada Lovelace')), 0, 1) == 1
'''


def session_rows(project):
    files = sorted((project / '.pi/sessions').glob('*.jsonl'))
    rows = []
    if files:
        for line in files[0].read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def text_of(content):
    if isinstance(content, str):
        return content
    return '\n'.join(c.get('text', '') for c in content or [] if isinstance(c, dict) and c.get('type') == 'text')


def text_workflow(rows):
    added_ids, listed_ids, completed_ids = set(), set(), set()
    final = ''
    for row in rows:
        msg = row.get('message') or {}
        if msg.get('role') == 'assistant' and text_of(msg.get('content')).strip():
            final = text_of(msg.get('content'))
        if msg.get('role') != 'toolResult' or msg.get('toolName') != 'todo' or msg.get('isError'):
            continue
        details = msg.get('details') or {}
        for todo in details.get('todos', []):
            if todo.get('text') != TODO or todo.get('id') is None:
                continue
            todo_id = todo['id']
            if details.get('action') == 'add' and todo.get('done') is False:
                added_ids.add(todo_id)
            elif details.get('action') == 'list' and todo_id in added_ids and todo.get('done') is False:
                listed_ids.add(todo_id)
            elif details.get('action') in ('toggle', 'complete', 'done') and todo_id in listed_ids and todo.get('done') is True:
                completed_ids.add(todo_id)
    lines = final.splitlines()
    tables = []
    for i in range(1, len(lines) - 1):
        delimiter = lines[i].strip().strip('|')
        cells = [cell.strip() for cell in delimiter.split('|')]
        if len(cells) >= 2 and all(re.fullmatch(r':?-{3,}:?', cell) for cell in cells) and '|' in lines[i - 1]:
            j = i + 1
            while j < len(lines) and '|' in lines[j]:
                tables.append(lines[j]); j += 1
    return {
        'todo_created_exact_multiline': bool(added_ids),
        'todo_listed_before_completion': bool(listed_ids),
        'same_todo_completed': bool(completed_ids),
        'final_markdown_table': bool(tables),
        'table_contains_expected_text': any(GREETING.strip() in line for line in tables),
    }


def parallel_workflow(rows):
    calls = {}
    accepted = []
    run_ids = []
    for row in rows:
        msg = row.get('message') or {}
        if msg.get('role') == 'assistant':
            for c in msg.get('content') or []:
                if c.get('type') != 'toolCall' or c.get('name') != 'subagent':
                    continue
                args = c.get('arguments') or {}
                tasks = (args.get('args') or {}).get('tasks') or []
                if args.get('workflow') == 'parallel' and len(tasks) == 2 and all(t.get('agent') == 'qwen' for t in tasks):
                    calls[c.get('id')] = args
        elif msg.get('role') == 'toolResult' and msg.get('toolName') == 'subagent' and msg.get('toolCallId') in calls:
            details = msg.get('details') or {}
            run_id = details.get('runId') or details.get('asyncId')
            if msg.get('isError') is False and (run_id or details.get('results')):
                accepted.append(msg['toolCallId'])
                if run_id:
                    run_ids.append(run_id)
    return {'two_qwen_parallel_launch_succeeded': bool(accepted)}, run_ids


def run_check(command, project, out_file, timeout=60, record_command=False, pythonpath='project'):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    if pythonpath == 'project':
        env['PYTHONPATH'] = str(project)
    else:
        env.pop('PYTHONPATH', None)
    try:
        run = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True, timeout=timeout)
        output, status = run.stdout + run.stderr, run.returncode
    except subprocess.TimeoutExpired:
        output, status = 'Independent check timed out.\n', 124
    except OSError as error:
        output, status = str(error) + '\n', 127
    out_file.parent.mkdir(parents=True, exist_ok=True)
    header = ('$ ' + shlex.join(command) + '\nPYTHONDONTWRITEBYTECODE=1; PYTHONPATH='
              + (str(project) if pythonpath == 'project' else '<unset>') + '\n\n') if record_command else ''
    out_file.write_text(header + output)
    return status, output


def test_runner(path):
    """Use the framework the retained test file actually imports, never plain-file no-op execution."""
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError):
        return 'unittest'
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split('.')[0])
    if 'pytest' in imports:
        return 'pytest'
    if 'unittest' in imports:
        return 'unittest'
    if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_') for node in tree.body):
        return 'pytest'
    return 'unittest'


def pytest_interpreter(project, fallback):
    """Reuse a project environment that already contains pytest; never install anything."""
    candidates = [project / '.venv/bin/python', project / 'venv/bin/python']
    candidates += [cfg.parent / 'bin/python' for cfg in sorted((project / '.pi').rglob('pyvenv.cfg'))]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            if list((candidate.parent.parent / 'lib').glob('python*/site-packages/pytest/__init__.py')):
                return str(candidate)
    return fallback


def retained_module_tests(project, out, interpreter):
    paths = []
    excluded = {'node_modules', 'site-packages', 'dist-packages', '__pycache__', '__pypackages__', 'venv', 'env'}
    for directory, dirs, files in os.walk(project):
        base = Path(directory)
        dirs[:] = [name for name in dirs if not name.startswith('.') and name not in excluded
                   and not (base / name / 'pyvenv.cfg').exists()]
        for name in files:
            path = base / name
            if not name.endswith('.py') or name.startswith('.') or name == 'integration_test.py' or path.is_symlink():
                continue
            conventional = name.startswith('test') or name.endswith(('_test.py', '_tests.py'))
            try:
                tree = ast.parse(path.read_text())
            except (OSError, SyntaxError):
                if conventional:
                    paths.append(path)
                continue
            has_cases = any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_')
                or isinstance(node, ast.ClassDef) and any(
                    isinstance(parent, ast.Attribute) and parent.attr == 'TestCase'
                    or isinstance(parent, ast.Name) and parent.id == 'TestCase' for parent in node.bases)
                for node in ast.walk(tree))
            if has_cases:
                paths.append(path)
    paths.sort()
    checks, details = {'at_least_two_retained_module_test_files': len(paths) >= 2}, {}
    for path in paths:
        name = path.relative_to(project).as_posix()
        runner = test_runner(path)
        selected = pytest_interpreter(project, interpreter) if runner == 'pytest' else interpreter
        pythonpath = 'project'
        if runner == 'pytest':
            console = Path(selected).parent / 'pytest'
            prefix = [str(console)] if console.is_file() and os.access(console, os.X_OK) else [selected, '-B', '-m', 'pytest']
            command = prefix + ['-p', 'no:cacheprovider', name, '-v']
            # Match the observed activated-venv console command. Injecting project PYTHONPATH or
            # replacing the console with -m changes when a local numbers.py shadows the stdlib.
            pythonpath = 'remove'
        else:
            parent = path.parent.relative_to(project).as_posix()
            command = [selected, '-B', '-m', 'unittest', 'discover', '-s', parent, '-p', path.name, '-v']
        output_file = out / 'module-test-output' / Path(name).with_suffix('.txt')
        status, output = run_check(command, project, output_file, record_command=True, pythonpath=pythonpath)
        pattern = r'\b(\d+) passed\b' if runner == 'pytest' else r'\bRan (\d+) tests?\b'
        count = re.search(pattern, output)
        passed = status == 0 and count is not None and int(count.group(1)) > 0
        checks[name + '_executed_and_passed'] = passed
        details[name] = {'command': command, 'exit': status, 'framework': runner, 'passed': passed,
                         'environment': {'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(project) if pythonpath == 'project' else None},
                         'tests_passed': int(count.group(1)) if passed else 0,
                         'output_file': str(output_file),
                         'failure': output.strip().splitlines()[-1] if not passed and output.strip() else None}
    (out / 'module-tests.json').write_text(json.dumps(details, indent=2))
    return checks, details


def score_run(work, arm, name, interpreter=None):
    work = Path(work)
    interpreter = interpreter or sys.executable
    project = work / (arm + '-' + name)
    out = work / 'reports' / arm / name
    out.mkdir(parents=True, exist_ok=True)
    rows = session_rows(project)
    task = name.split('.')[0]
    check = work / 'coding/checks' / (task + '.py')
    functional = None
    checks, launch_ids, diagnostics = {}, [], {}
    status, output = None, ''
    if check.exists():
        status, output = run_check([interpreter, '-B', str(check)], project, out / 'check.txt')
        functional = status == 0
    elif task == 'text-tools':
        path = project / 'greeting.txt'
        functional = path.is_file() and path.read_bytes() == GREETING.encode('utf-8')
        checks = text_workflow(rows)
        # The request asks for a result table, not for the literal file contents in a table cell.
        diagnostics['table_contains_expected_text'] = checks.pop('table_contains_expected_text')
    elif task == 'parallel':
        status, output = run_check([interpreter, '-B', '-c', PARALLEL_CHECK], project, out / 'check.txt')
        functional = status == 0
        checks, launch_ids = parallel_workflow(rows)
        checks['requested_numbers_module_present'] = (project / 'numbers.py').is_file()
        checks['requested_words_module_present'] = (project / 'words.py').is_file()
        module_checks, module_details = retained_module_tests(project, out, interpreter)
        checks.update(module_checks)
        diagnostics['retained_module_tests'] = module_details
        checks['integration_test_present'] = (project / 'integration_test.py').is_file()
        integration_status, integration_output = run_check(
            [interpreter, '-B', '-m', 'unittest', 'integration_test', '-v'], project, out / 'integration-check.txt')
        match = re.search(r'\bRan (\d+) tests?\b', integration_output)
        checks['integration_test_executed_and_passed'] = integration_status == 0 and match is not None and int(match.group(1)) > 0
    return {
        'version': 6,
        'functional_pass': functional,
        'functional_exit': status,
        'functional_failure': output.strip().splitlines()[-1] if status not in (None, 0) and output.strip() else None,
        'workflow_checks': checks,
        'workflow_pass': all(checks.values()) if checks else None,
        'overall_pass': functional is True and all(checks.values()),
        'diagnostics': diagnostics,
        'successful_parallel_run_ids': launch_ids,
        'check_interpreter': interpreter,
    }


def main():
    work = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name('treadmill-work').read_text().strip())
    arms = sys.argv[2:] or sorted(p.name for p in (work / 'reports').iterdir() if p.is_dir())
    for arm in arms:
        scored = []
        for path in sorted((work / 'reports' / arm).glob('*/result.json')):
            row = json.loads(path.read_text())
            row.setdefault('original_scorer_pass', row.get('pass'))
            row['scoring'] = score_run(work, arm, row['run'])
            row['pass'] = row['scoring']['functional_pass']
            path.write_text(json.dumps(row, indent=2))
            scored.append(row)
            print(json.dumps(row), flush=True)
        if scored:
            (work / 'reports' / arm / 'rescored-results.json').write_text(json.dumps(scored, indent=2))


if __name__ == '__main__':
    main()
