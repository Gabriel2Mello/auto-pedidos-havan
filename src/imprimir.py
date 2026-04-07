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
    c = canvas.Canvas(packet, pagesize=(largura, altura))

    margem_altura = 60
    margem_largura = 50

    c.saveState()
    c.translate(largura, 0)
    c.rotate(90)

    x = altura - margem_altura
    y = largura - margem_largura

    c.setFont('Helvetica', 12)
    largura_texto = c.stringWidth(texto, 'Helvetica', 12)
    c.drawString(x - largura_texto, y, texto)

    c.restoreState()
    c.save()

    packet.seek(0)
    return PdfReader(packet).pages[0]


def adicionar_numero(pdf_entrada, pdf_saida, numero):
    writer = PdfWriter()

    with open(pdf_entrada, 'rb') as f_entrada:
        reader = PdfReader(f_entrada)

        primeira_pag = reader.pages[0]
        largura = float(primeira_pag.mediabox.width)
        altura = float(primeira_pag.mediabox.height)

        overlay = criar_overlay(str(numero), largura, altura)

        for page in reader.pages:
            page.merge_page(overlay)
            writer.add_page(page)

        with open(pdf_saida, 'wb') as f_saida:
            writer.write(f_saida)


def imprimir_pdf(caminho):
    try:
        logger.info(f'Enviando para impressora: {IMPRESSORA}')
        subprocess.run([
            str(SUMATRA),
            '-print-to', IMPRESSORA,
            '-print-settings', 'simplex',
            '-exit-on-print',
            str(caminho)
        ], check=True)
        sleep(1.5)

    except subprocess.CalledProcessError as e:
        logger.error(f'Erro ao imprimir {caminho}: {e}')


def processar_impressao(pedido, numero_interno):
    caminho_pedido = BASE_PATH_PEDIDOS / pedido

    pdf_original = caminho_pdf(pedido)
    nome_final = f'{numero_interno} {pedido}.pdf'
    pdf_final = caminho_pedido / nome_final

    adicionar_numero(pdf_original, pdf_final, numero_interno)
    #imprimir_pdf(caminho_pedido / pdf_final)

