"""Compatibilidade para importacoes antigas; use os modulos especificos."""
from src.arquivos import (
    MAX_CARACTERES_MOTIVO as MAX_CARACTERES_MOTIVO,
    caminho_pdf as caminho_pdf, caminho_xml as caminho_xml, carregar_xml as carregar_xml,
    extrair_xml as extrair_xml, obter_diretorio_executavel as obter_diretorio_executavel,
    formatar_motivo_erro as formatar_motivo_erro, normalizar_motivo as normalizar_motivo,
    salvar_pedido_txt as salvar_pedido_txt,
)
from src.erros import (
    LoginInvalidoError as LoginInvalidoError, SessaoPortalExpiradaError as SessaoPortalExpiradaError,
    SisplanError as SisplanError,
)
from src.notificacoes import enviar_alerta_teams as enviar_alerta_teams
from src.windows import (
    set_app_id as set_app_id, send_keys_sleep as send_keys_sleep, aguardar_campo as aguardar_campo,
)
from src.pedidos import normalizar_pedidos


def input_pedido() -> list[str] | None:
    return normalizar_pedidos(input('Pedido: ')) or None
