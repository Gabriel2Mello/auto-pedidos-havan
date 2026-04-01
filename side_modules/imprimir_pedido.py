import io
import subprocess
from time import sleep
from os import getcwd
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter
from pathlib import Path


def criar_overlay(texto, largura, altura):
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(largura, altura))

    margem_altura = 60
    margem_largura = 40

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


def adicionar_numero(entrada, saida, numero):
    reader = PdfReader(entrada)
    writer = PdfWriter()

    for page in reader.pages:
        largura = float(page.mediabox.width)
        altura = float(page.mediabox.height)

        overlay = criar_overlay(str(numero), largura, altura)

        page.merge_page(overlay.pages[0])
        writer.add_page(page)

    with open(saida, 'wb') as f:
        writer.write(f)


def imprimir_pdf(caminho_pdf, impressora):
    sumatra_path = r'C:\Users\ADM07\SumatraPDF\SumatraPDF.exe'

    try:
        subprocess.run([
            sumatra_path,
            '-print-to', impressora,
            '-print-settings', 'simplex',
            '-exit-on-print',
            caminho_pdf
        ], check=True)
        sleep(1)

    except subprocess.CalledProcessError as e:
        print('Erro ao imprimir:', e)



base_dir = Path(getcwd())
entrada = base_dir / 'Ordem de compra 2026-29276.pdf'
saida = base_dir / 'saida.pdf'
numero = '12345'
#impressora = 'EPSON3B3537 (L4260 Series)'
impressora = 'HP LaserJet MFP M426dw (FC6312)-1'

adicionar_numero(entrada, saida, numero)
imprimir_pdf(saida, impressora)
