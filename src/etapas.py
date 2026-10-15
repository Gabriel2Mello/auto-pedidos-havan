"""Estados persistidos e classificacao unica das filas."""
from typing import Literal

Etapa = Literal[
    'para_baixar', 'baixado', 'importacao_iniciada', 'gravacao_pendente',
    'importado', 'pdf_pronto', 'impressao_pendente', 'impressao_iniciada',
    'impressao_incerta', 'impressao_enviada', 'existente',
]
ETAPAS = (
    'para_baixar', 'baixado', 'importacao_iniciada', 'gravacao_pendente',
    'importado', 'pdf_pronto', 'impressao_pendente', 'impressao_iniciada',
    'impressao_incerta', 'impressao_enviada', 'existente',
)

ETAPAS_FINAIS = ('impressao_enviada', 'existente')
INCLUSOES_INCERTAS = ('importacao_iniciada', 'gravacao_pendente')
ETAPAS_INICIAIS = ('para_baixar', 'baixado')

ROTULOS: dict[str, str] = {
    'para_baixar': 'A baixar', 'baixado': 'Baixado',
    'importacao_iniciada': 'Conferir inclusão', 'gravacao_pendente': 'Gravação não confirmada',
    'importado': 'Importação confirmada', 'pdf_pronto': 'PDF pronto',
    'impressao_pendente': 'Impressão pendente', 'impressao_iniciada': 'Enviando impressão',
    'impressao_incerta': 'Conferir impressão', 'impressao_enviada': 'Enviado para impressão',
    'existente': 'Já existe no Sisplan',
}


def fila_da_etapa(etapa: str) -> str:
    if etapa not in ETAPAS:
        raise ValueError('Etapa desconhecida: ' + etapa)
    if etapa == 'para_baixar':
        return 'para_baixar'
    if etapa in ('baixado', *INCLUSOES_INCERTAS):
        return 'baixados'
    return 'enviados' if etapa == 'impressao_enviada' else 'importados'
