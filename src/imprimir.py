import io
import subprocess
from time import sleep
from pypdf import PdfReader, PdfWriter

from reportlab.pdfgen import canvas

from src.config import (
    SUMATRA,
    IMPRESSORA,
    BASE_PATH_PEDIDOS
)
from src.utils import caminho_pdf

def criar_overlay(texto, largura, altura):
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(largura, altura))

    margem_altura = 60
    margem_largura = 50

    c.translate(largura, 0)
    c.rotate(90)

    x = altura - margem_altura
    y = largura - margem_largura

    c.setFont('Helvetica', 12)
    largura_texto = c.stringWidth(texto, 'Helvetica', 12)
    c.drawString(x - largura_texto, y, texto)

    c.save()
    packet.seek(0)

    return PdfReader(packet)


def adicionar_numero(pdf_entrada, pdf_saida, numero):
    reader = PdfReader(pdf_entrada)
    writer = PdfWriter()

    for page in reader.pages:
        largura = float(page.mediabox.width)
        altura = float(page.mediabox.height)

        overlay = criar_overlay(str(numero), largura, altura)

        page.merge_page(overlay.pages[0])
        writer.add_page(page)

    with open(pdf_saida, 'wb') as f:
        writer.write(f)


def imprimir_pdf(caminho):
    try:
        subprocess.run([
            SUMATRA,
            '-print-to', IMPRESSORA,
            '-print-settings', 'simplex',
            '-exit-on-print',
            caminho
        ], check=True)
        sleep(1)

    except subprocess.CalledProcessError as e:
        print('Erro ao imprimir:', e)


def imprimir_pedido(pedido, numero_interno):
    caminho_pedidos = BASE_PATH_PEDIDOS / pedido

    pdf_entrada = caminho_pdf(pedido)
    pdf_saida = caminho_pedidos / f'{numero_interno} {pedido}.pdf'

    adicionar_numero(pdf_entrada, pdf_saida, numero_interno)

    #imprimir_pdf(caminho_pedidos / pdf_saida)

