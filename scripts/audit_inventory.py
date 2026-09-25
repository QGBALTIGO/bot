"""Offline source inventory. Does not import the app, access accounts, or contact services."""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def inventory():
    functions, endpoints, commands, callbacks, async_io, duplicates = [], [], [], [], [], []
    sources = [p for p in ROOT.rglob('*.py') if not any(x in p.parts for x in ('.git', 'node_modules', '__pycache__'))]
    for path in sources:
        relative = str(path.relative_to(ROOT))
        if relative.startswith(('tests/', 'scripts/')):
            continue
        tree = ast.parse(path.read_text(encoding='utf8'))
        names = {}
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if n.name in names: duplicates.append({'file': relative, 'function': n.name, 'lines': [names[n.name], n.lineno]})
                names[n.name] = n.lineno
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({'file': relative, 'name': n.name, 'line': n.lineno, 'end': n.end_lineno, 'async': isinstance(n, ast.AsyncFunctionDef)})
                for d in n.decorator_list:
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ('get','post','put','patch','delete') and d.args and isinstance(d.args[0], ast.Constant):
                        endpoints.append({'file': relative,'function': n.name,'line': n.lineno,'method': d.func.attr.upper(),'path': d.args[0].value})
            if not isinstance(n, ast.Call): continue
            fn = ast.unparse(n.func)
            if fn.endswith('add_api_route') and n.args:
                endpoints.append({'file':relative,'line':n.lineno,'function':ast.unparse(n.args[1]) if len(n.args)>1 else '', 'path':ast.literal_eval(n.args[0]) if isinstance(n.args[0],ast.Constant) else ast.unparse(n.args[0]),'method': next((ast.unparse(k.value) for k in n.keywords if k.arg=='methods'),'GET')})
            if fn == 'CommandHandler' and len(n.args)>1:
                commands.append({'file':relative,'command':ast.literal_eval(n.args[0]),'handler':ast.unparse(n.args[1]),'line':n.lineno})
            if fn == 'CallbackQueryHandler':
                callbacks.append({'file':relative,'handler':ast.unparse(n.args[0]),'pattern': next((ast.unparse(k.value) for k in n.keywords if k.arg=='pattern'),None),'line':n.lineno})
    return {'scope':'static inventory, not proof of behavioral coverage','python_files':len({x['file'] for x in functions}),'function_count':len(functions),'functions':functions,'route_declarations':endpoints,'commands':commands,'callbacks':callbacks,'duplicate_top_level_functions':duplicates, 'frontend_pages':sorted(str(p.relative_to(ROOT)) for p in (ROOT/'aninexus_frontend/src/pages').rglob('*.tsx'))}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    report=inventory();args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v if not isinstance(v,list) else len(v) for k,v in report.items()},ensure_ascii=False))
