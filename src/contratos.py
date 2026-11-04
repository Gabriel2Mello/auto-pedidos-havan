"""Contratos compartilhados pelas interfaces e pelo servico."""
from typing import Callable, Literal

Modo = Literal['normal', 'retomar', 'preparar', 'revalidar', 'importar', 'recuperar', 'reiniciar']
ModoWeb = Literal['normal', 'retomar', 'preparar', 'revalidar', 'importar', 'recuperar']
DecisaoErro = Literal['repetir', 'pular', 'encerrar']
AoErro = Callable[[str, Exception, bool, bool], DecisaoErro]
AoProgresso = Callable[[str, int, int], None]
