"""Small strict parsers for existing JSON endpoints without a schema migration."""
import re
from fastapi import HTTPException

def body_integer(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise HTTPException(400, "Use um número inteiro válido.")
    if isinstance(value, str) and (len(value) > 20 or re.fullmatch(r"-?[0-9]+", value) is None):
        raise HTTPException(400, "Use um número inteiro válido.")
    number = int(value)
    if not -(2**63) < number < 2**63:
        raise HTTPException(400, "Número fora do limite permitido.")
    return number
