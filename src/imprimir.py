import io
import subprocess
import os
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter, PageObject

from src.logs import get_logger
from src.config import configuracao_atual
from src.arquivos import (caminho_pdf)
from src.estado import EstadoError, EstadoPedidos

logger = get_logger(__name__)


def processar_impressao(
    pedido: str, numero: str, historico: EstadoPedidos, forcar: bool = False,
) -> str:
    registro = historico.obter(pedido)
    if registro is None or registro.numero != numero or registro.etapa == 'gravacao_pendente':
        raise EstadoError('Impressão bloqueada: pedido sem gravação confirmada no histórico.')
    if registro.etapa == 'impressao_enviada' and not forcar:
        return 'impressao_enviada'
    if registro.etapa in ('impressao_iniciada', 'impressao_incerta') and not forcar:
        motivo = 'Envio anterior incerto; confira a fila antes de usar --reimprimir.'
        historico.salvar(replace(registro, etapa='impressao_incerta', erro=motivo))
        logger.warning('Pedido %s: %s', pedido, motivo)
        return 'impressao_incerta'

    try:
        caminho_diretorio = configuracao_atual().pasta_pedidos / pedido
        caminho_diretorio.mkdir(parents=True, exist_ok=True)
        pdf_final = Path(registro.pdf) if registro.pdf else caminho_diretorio / f'{numero} {pedido}.pdf'
        pronto = False
        if pdf_final.is_file():
            try:
                reader = PdfReader(pdf_final)
                pronto = bool(reader.pages) and (reader.metadata or {}).get('/Title') == f'Pedido {numero}'
            except Exception:
                pronto = False
        if not pronto and not adicionar_numero(caminho_pdf(pedido), pdf_final, numero):
            historico.salvar(replace(
                registro, etapa='impressao_pendente', pdf='', erro='Falha ao gerar o PDF numerado.',
            ))
            return 'impressao_pendente'
        registro = replace(registro, etapa='pdf_pronto', pdf=str(pdf_final.resolve()), erro='')
        historico.salvar(registro)
    except EstadoError:
        raise
    except Exception as error:
        logger.exception('Pedido %s: falha ao preparar a impressão.', pedido)
        historico.salvar(replace(registro, etapa='impressao_pendente', erro=str(error)))
        return 'impressao_pendente'

    # Se o processo cair após enviar ao Sumatra, esta etapa impede reenvio automático.
    historico.salvar(replace(registro, etapa='impressao_iniciada'))
    resultado = imprimir_pdf(pdf_final)
    etapa = {
        'enviada': 'impressao_enviada', 'pendente': 'impressao_pendente',
        'incerta': 'impressao_incerta',
    }[resultado.situacao]
    historico.salvar(replace(registro, etapa=etapa, erro=resultado.motivo))
    return etapa


def adicionar_numero(
    pdf: Path,
    pdf_saida: Path,
    numero: str,
) -> bool:
    logger.debug(f"Adicionando '{numero}' no PDF: {pdf}")
    temporario: Path | None = None
    try:
        if not pdf.exists():
            logger.error(f'Arquivo não encontrado: {pdf}')
            return False

        with pdf.open('rb') as f:
            reader = PdfReader(f)
            writer = PdfWriter()

            if not reader.pages:
                logger.error(f'PDF {pdf.name} sem páginas')
                return False

            caixa = reader.pages[0].mediabox
            largura = float(caixa.width)
            altura = float(caixa.height)
            overlay = criar_overlay(numero, largura, altura)

            for page in reader.pages:
                page.merge_page(overlay)
                writer.add_page(page)

            writer.add_metadata({
                '/Title': f'Pedido {numero}',
                '/Producer': 'Python Auto Pedidos Havan'
            })

            with NamedTemporaryFile(dir=pdf_saida.parent, suffix='.tmp', delete=False) as f_out:
                temporario = Path(f_out.name)
                writer.write(f_out)
                f_out.flush()
                os.fsync(f_out.fileno())
            temporario.replace(pdf_saida)

        return True

    except Exception as error:
        logger.error('Falha ao processar %s: %s', pdf.name, error)
        return False
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)


@dataclass(frozen=True)
class ResultadoImpressao:
    situacao: Literal['enviada', 'pendente', 'incerta']
    motivo: str = ''


def imprimir_pdf(caminho: Path) -> ResultadoImpressao:
    try:
        if caminho.stat().st_size == 0:
            logger.error(f'Arquivo corrompido: {caminho}')
            return ResultadoImpressao('pendente', 'PDF vazio.')

        config = configuracao_atual()
        logger.debug('Imprimindo %s em: %s', caminho, config.impressora)
        args = [
            str(config.sumatra.resolve()),
            '-print-to', config.impressora,
            '-print-settings', 'fit,simplex',
            '-exit-on-print',
            str(caminho.resolve())
        ]

        subprocess.run(
            args,
            check=True,
            capture_output=True,
            timeout=15
        )
        logger.info('Impressão enviada ao SumatraPDF: %s', caminho.name)
        return ResultadoImpressao('enviada')

    except subprocess.TimeoutExpired:
        logger.error('SumatraPDF demorou demais para responder')
        return ResultadoImpressao('incerta', 'SumatraPDF excedeu o tempo; confira a fila de impressão.')

    except subprocess.CalledProcessError as error:
        error_msg = (
            error.stderr.decode('latin-1')
            if error.stderr
            else 'Erro desconhecido'
        )
        msg = 'Erro no SumatraPDF'
        logger.debug(f'{msg} para {caminho.name}: {error_msg}')
        logger.error(msg)
        return ResultadoImpressao('incerta', 'SumatraPDF retornou erro; confira a fila de impressão.')

    except OSError as error:
        logger.error('Não foi possível iniciar a impressão: %s', error)
        return ResultadoImpressao('pendente', str(error))

    except Exception as error:
        msg = 'Erro inesperado no Sumatra'
        logger.debug(f'{msg}: {error}')
        logger.error(msg)
        return ResultadoImpressao('incerta', msg)


def criar_overlay(
    texto: str,
    largura: float,
    altura: float,
) -> PageObject:
    packet = io.BytesIO()
    c = canvas.Canvas(
        packet,
        pagesize=(largura, altura),
        pageCompression=0
    )

    c.setFont('Helvetica-Bold', 12)
    largura_texto = c.stringWidth(texto, 'Helvetica-Bold', 12)

    c.saveState()
    c.translate(largura, 0)
    c.rotate(90)

    x_pos = altura - 60 - largura_texto
    y_pos = largura - 50

    c.setFillColorRGB(0, 0, 0)
    c.drawString(x_pos, y_pos, texto)

    c.restoreState()
    c.save()

    packet.seek(0)
    return PdfReader(packet).pages[0]

