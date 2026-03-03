Rastreamento (chamada mais recente):
  Arquivo "/app/.venv/bin/uvicorn", linha 8, em <módulo>
    sys.exit(main())
             ^^^^^^
  Arquivo "/app/.venv/lib/python3.11/site-packages/click/core.py", linha 1485, em __call__
    retornar self.main(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  Arquivo "/app/.venv/lib/python3.11/site-packages/click/core.py", linha 1406, em main
    rv = self.invoke(ctx)
         ^^^^^^^^^^^^^^^^
  Arquivo "/app/.venv/lib/python3.11/site-packages/click/core.py", linha 1269, em invoke
    retornar ctx.invoke(self.callback, **ctx.params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  Arquivo "/app/.venv/lib/python3.11/site-packages/click/core.py", linha 824, em invoke
    retornar callback(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  Arquivo "/app/.venv/lib/python3.11/site-packages/uvicorn/main.py", linha 433, em main
    correr(
  Arquivo "/app/.venv/lib/python3.11/site-packages/uvicorn/main.py", linha 606, em run
    servidor.executar()
  Arquivo "/app/.venv/lib/python3.11/site-packages/uvicorn/server.py", linha 75, em run
    return asyncio_run(self.serve(sockets=sockets), loop_factory=self.config.get_loop_factory())
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  Arquivo "/app/.venv/lib/python3.11/site-packages/uvicorn/_compat.py", linha 30, em asyncio_run
    retornar runner.run(main)
           ^^^^^^^^^^^^^^^^
  Arquivo "/mise/installs/python/3.11.9/lib/python3.11/asyncio/runners.py", linha 118, em run
    retornar self._loop.run_until_complete(tarefa)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  Arquivo "/mise/installs/python/3.11.9/lib/python3.11/asyncio/base_events.py", linha 654, em run_until_complete
    retornar futuro.resultado()
           ^^^^^^^^^^^^^^^
  Arquivo "/mise/installs/python/3.11.9/lib/python3.11/importlib/__init__.py", linha 126, em import_module
  Arquivo "/app/.venv/lib/python3.11/site-packages/uvicorn/config.py", linha 441, em load
  Arquivo "/app/.venv/lib/python3.11/site-packages/uvicorn/server.py", linha 79, em serve
    retornar _bootstrap._gcd_import(nome[nível:], pacote, nível)
    self.loaded_app = import_from_string(self.app)
    aguarde self._serve(sockets)
  Arquivo "/app/.venv/lib/python3.11/site-packages/uvicorn/importer.py", linha 19, em import_from_string
  Arquivo "/app/.venv/lib/python3.11/site-packages/uvicorn/server.py", linha 86, em _serve
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    módulo = importlib.import_module(module_str)
    config.load()
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
^^
  Arquivo "<frozen importlib._bootstrap>", linha 1204, em _gcd_import
  Arquivo "<frozen importlib._bootstrap>", linha 1176, em _find_and_load
  Arquivo "<frozen importlib._bootstrap>", linha 1147, em _find_and_load_unlocked
  Arquivo "<frozen importlib._bootstrap>", linha 690, em _load_unlocked
  Arquivo "<frozen importlib._bootstrap_external>", linha 940, em exec_module
  Arquivo "<frozen importlib._bootstrap>", linha 241, em _call_with_frames_removed
  Arquivo "/app/webapp.py", linha 3, em <módulo>
    @app.get("/app", response_class=HTMLResponse)
     ^^^
NameError: o nome 'app' não está definido
