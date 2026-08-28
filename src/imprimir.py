import io
import subprocess
from pathlib import Path
from time import sleep

from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter, PageObject

from src.logs import get_logger
from src.config import (
    SUMATRA,
    IMPRESSORA,
    BASE_PATH_PEDIDOS,
)
from src.utils import caminho_pdf

logger = get_logger(__name__)


def processar_impressao(pedido: str, numero: str) -> None:
    logger.info('Imprimindo')

    caminho_diretorio = BASE_PATH_PEDIDOS / pedido
    caminho_diretorio.mkdir(parents=True, exist_ok=True)

    pdf = caminho_pdf(pedido)
    pdf_final = caminho_diretorio / f'{numero} {pedido}.pdf'

    try:
        if adicionar_numero(pdf, pdf_final, numero):
            imprimir_pdf(pdf_final)

    except Exception as error:
        logger.error('Erro no processamento de impressão: %s', error)


def adicionar_numero(
    pdf: Path,
    pdf_saida: Path,
    numero: str,
) -> bool:
    logger.debug(f"Adicionando '{numero}' no PDF: {pdf}")
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

            with pdf_saida.open('wb') as f_out:
                writer.write(f_out)

        return True

    except Exception as error:
        logger.error('Falha ao processar %s: %s', pdf.name, error)
        return False


def imprimir_pdf(caminho: Path) -> None:
    try:
        if caminho.stat().st_size == 0:
            logger.error(f'Arquivo corrompido: {caminho}')
            return

        logger.debug(f'Imprimindo {caminho} em: {IMPRESSORA}')
        args = [
            str(SUMATRA.resolve()),
            '-print-to', IMPRESSORA,
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
        sleep(1)
        logger.info('Sucesso')

    except subprocess.TimeoutExpired:
        logger.error('SumatraPDF demorou demais para responder')

    except subprocess.CalledProcessError as error:
        error_msg = (
            error.stderr.decode('latin-1')
            if error.stderr
            else 'Erro desconhecido'
        )
        msg = 'Erro no SumatraPDF'
        logger.debug(f'{msg} para {caminho.name}: {error_msg}')
        logger.error(msg)

    except Exception as error:
        msg = 'Erro inesperado no Sumatra'
        logger.debug(f'{msg}: {error}')
        logger.error(msg)


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

