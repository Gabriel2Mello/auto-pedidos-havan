import io
import subprocess
import logging
from time import sleep
from pypdf import PdfReader, PdfWriter

from reportlab.pdfgen import canvas

from src.config import (
    SUMATRA,
    IMPRESSORA,
    BASE_PATH_PEDIDOS
)
from src.utils import caminho_pdf

logger = logging.getLogger(__name__)


def criar_overlay(texto, largura, altura):
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


def adicionar_numero(pdf_entrada, pdf_saida, numero):
    writer = PdfWriter()

    try:
        with open(pdf_entrada, 'rb') as f:
            reader = PdfReader(f)
            if not reader.pages:
                return

            caixa = reader.pages[0].mediabox
            largura = float(caixa.width)
            altura = float(caixa.height)

            overlay = criar_overlay(str(numero), largura, altura)

            for page in reader.pages:
                page.merge_page(overlay)
                writer.add_page(page)

            writer.add_metadata({
                '/Title': f'Pedido {numero}',
                '/Producer': 'Python Autocofre High Quality'
            })

            with open(pdf_saida, 'wb') as f_out:
                writer.write(f_out)

    except Exception as e:
        logger.error(f'Falha ao processar PDF {pdf_entrada}: {e}')
        raise


def imprimir_pdf(caminho):
    if not caminho.exists():
        logger.error(f'Arquivo não encontrado para impressão: {caminho}')
        return

    try:
        logger.info(f'Imprimindo {caminho.name} em: {IMPRESSORA}')
        args = [
            str(SUMATRA),
            '-print-to', IMPRESSORA,
            '-print-settings', 'simplex',
            '-exit-on-print',
            str(caminho)
        ]

        subprocess.run(args, check=True, capture_output=True)
        sleep(1.2)

    except subprocess.CalledProcessError as e:
        logger.error(f'Erro no SumatraPDF para {caminho.name}: {e.stderr.decode()}')


def processar_impressao(pedido, numero_interno):
    caminho_diretorio = BASE_PATH_PEDIDOS / pedido
    caminho_diretorio.mkdir(parents=True, exist_ok=True)

    pdf_original = caminho_pdf(pedido)
    pdf_final = caminho_diretorio / f'{numero_interno} {pedido}.pdf'

    try:
        adicionar_numero(pdf_original, pdf_final, numero_interno)
        imprimir_pdf(pdf_final)
    except Exception as e:
        logger.error(f'Erro no processamento de impressão do pedido: {pedido}: {e}')

