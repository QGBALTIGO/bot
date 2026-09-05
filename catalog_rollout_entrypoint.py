from utils.catalog_safe_rollout import prepare_runtime_safe_catalog

# Materializa apenas as adições seguras antes de qualquer módulo de cards ser importado.
# Se o manifesto estiver inválido/incompleto, o bot continua com o catálogo antigo.
prepare_runtime_safe_catalog()

from webapp_entrypoint import app  # noqa: E402,F401
