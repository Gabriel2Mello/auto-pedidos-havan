"""Contratos compartilhados pelas interfaces e pelo servico."""
from typing import Callable, Literal

Modo = Literal['normal', 'retomar', 'reimprimir', 'reiniciar']
ModoWeb = Literal['normal', 'retomar', 'reimprimir']
DecisaoErro = Literal['repetir', 'pular', 'encerrar']
AoErro = Callable[[str, Exception, bool, bool], DecisaoErro]
AoProgresso = Callable[[str, int, int], None]
