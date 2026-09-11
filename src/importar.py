from time import sleep
from typing import cast

from pywinauto import WindowSpecification

from src.logs import get_logger
from src.config import (
    COORD_ABA_PEDIDO,
    COORD_ITENS_PEDIDO,
    ATALHOS,
)
from src.handle_app import (
    importa_arq_integracao,
    handle_aviso_duplicado,
    handle_produto_sem_cadastro,
)
from src.pedidos import definir_empresa, extrair_dados_xml
from src.utils import (
    caminho_xml,
    carregar_xml,
    SisplanError,
    salvar_pedido_txt,
    enviar_alerta_teams,
    send_keys_sleep,
    aguardar_campo,
)

logger = get_logger(__name__)

CamposSisplan = dict[str, WindowSpecification]


OPERACOES_ESPECIAIS = {
    'ITENS PROMOCIONAIS PARA COMERCIALIZACAO': (
        'PROMOCIONAL',
        'PEDIDO PROMOCIONAL',
    ),
    'BONIFICACAO COMERCIAL': ('BONIFICADO', 'PEDIDO BONIFICADO'),
}


def importar_pedido(
    pedido: str,
    pedido_grade: WindowSpecification,
    aba_pedido: WindowSpecification,
    grid: WindowSpecification,
    campos: CamposSisplan,
) -> tuple[str, bool]:
    logger.info_split(f'Importando: {pedido}')

    try:
        pedido_grade.click_input(coords=COORD_ABA_PEDIDO)
        send_keys_sleep(ATALHOS['incluir'], 0.3)

        aguardar_campo(campos['numero']).type_keys('{TAB}')
        numero_interno: str = cast(str, campos['numero'].window_text())

        xml_path = caminho_xml(pedido)
        xml_root = carregar_xml(xml_path)
        dados_xml = extrair_dados_xml(xml_root)

        preencher_dados_fixos(campos)

        if definir_empresa(dados_xml['produto']) == 'MATRIZ':
            selecionar_empresa_matriz(campos['empresa'])

        preencher_datas(
            campos,
            dados_xml['data_fatura'],
            dados_xml['data_entrega']
        )

        aba_pedido.click_input(coords=COORD_ITENS_PEDIDO)

        grid.click_input(button='right')  # Abre as opções do grid.
        send_keys_sleep(ATALHOS['importar'])
        send_keys_sleep(ATALHOS['havan'])

        importa_arq_integracao(xml_path)
        sem_cadastro = handle_produto_sem_cadastro(pedido)

        pedido_grade.click_input(coords=COORD_ABA_PEDIDO)

        if sem_cadastro:
            send_keys_sleep(ATALHOS['desistir'], 0.2)
            send_keys_sleep(ATALHOS['sim'])
            enviar_alerta_teams(pedido, '', 'PRODUTO SEM CADASTRO')

            return '', sem_cadastro

        processar_operacao_comercial(
            dados_xml['operacao'],
            pedido,
            numero_interno,
            campos
        )
        send_keys_sleep(ATALHOS['gravar'])
        invalido = handle_aviso_duplicado()

        return numero_interno, invalido

    except Exception as error:
        logger.debug('Erro no Sisplan: %s', error, exc_info=True)
        raise SisplanError() from error


def processar_operacao_comercial(
    operacao_alvo: str,
    pedido: str,
    numero_interno: str,
    campos: CamposSisplan,
) -> None:
    operacao = OPERACOES_ESPECIAIS.get(operacao_alvo)
    if operacao is None:
        return

    observacao, mensagem = operacao
    aguardar_campo(campos['observacao_2']).set_text(observacao)
    logger.info(mensagem)

    sleep(0.1)
    salvar_pedido_txt(pedido, True)
    enviar_alerta_teams(pedido, numero_interno, mensagem)


def preencher_dados_fixos(campos: CamposSisplan) -> None:
    dados = {
        'cliente':       '00022',
        'representante': '00001',
        'transporte':    '00001',
        'tabela_preco':  '004',
        'historico':     '02',
        'tipo_venda':    '1',
        'operacao':      '1',
    }

    for nome, valor in dados.items():
        aguardar_campo(campos[nome]).set_text(valor)

    aguardar_campo(campos['classe_gerencial']).set_focus()
    campos['classe_gerencial'].type_keys('20001{TAB}')
    sleep(0.3)


def preencher_datas(
    campos: CamposSisplan,
    data_fatura: str,
    data_entrega: str,
) -> None:
    aguardar_campo(campos['data_entrega']).set_text(data_entrega)
    aguardar_campo(campos['data_saida']).set_text(data_entrega)
    aguardar_campo(campos['data_fatura']).set_text(data_fatura)


def selecionar_empresa_matriz(combo_empresa: WindowSpecification) -> None:
    aguardar_campo(combo_empresa).set_focus()
    combo_empresa.type_keys('{UP}')

