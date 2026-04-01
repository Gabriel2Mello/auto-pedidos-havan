from pathlib import Path
from os import environ

UNRAR_TOOL = environ['UNRAR_TOOL']
CNPJ_MATRIZ = environ['CNPJ_MATRIZ'],
SENHA_PORTAL = environ['SENHA_PORTAL']

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0'

ORIGIN = 'https://cliente.havan.com.br'
BASE_URL = ORIGIN + '/Fornecedor'
CONTENT_TYPE = 'application/x-www-form-urlencoded; charset=UTF-8'

BASE_PATH_PEDIDOS = Path(environ['HAVAN_PEDIDOS'])
