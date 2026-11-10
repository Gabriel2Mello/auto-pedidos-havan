"""Contratos compartilhados pelas interfaces e pelo servico."""
from typing import Callable, Literal

ModoWeb = Literal['normal', 'retomar', 'preparar', 'revalidar', 'importar', 'recuperar', 'liberar']
Modo = ModoWeb | Literal['reiniciar']
DecisaoErro = Literal['repetir', 'pular', 'encerrar']
AoErro = Callable[[str, Exception, bool, bool], DecisaoErro]
AoProgresso = Callable[[str, int, int], None]
