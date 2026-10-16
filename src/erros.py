"""Erros operacionais sem dependencias de GUI ou rede."""

class LoginInvalidoError(Exception):
    """Exceção para quando o site retorna 200, mas falhou o login"""

    def __init__(self, message: str = 'CNPJ ou senha inválidos') -> None:
        super().__init__(message)


class SessaoPortalExpiradaError(RuntimeError):
    """O portal voltou a exigir autenticação durante o processamento."""

    def __init__(self) -> None:
        super().__init__('A sessão do Portal Havan expirou. Reconecte para continuar ou pare o processamento.')


class SisplanError(Exception):
    def __init__(self, message: str = 'Falha na tela do Sisplan') -> None:
        super().__init__(message)


class NumeroInternoForaSequenciaError(SisplanError):
    """Duas inclusões com número suspeito foram canceladas antes da gravação."""


class EstadoError(RuntimeError):
    """Não foi possível preservar o histórico; não repetir ações incertas."""


class EstadoEmUsoError(EstadoError):
    """Outra execução ainda possui a trava do histórico local."""


class BancoSisplanError(RuntimeError):
    """Falha de acesso ao banco: a importação não pode prosseguir."""


class PedidoRejeitadoError(RuntimeError):
    """O pedido permanece na fila até o problema ser corrigido."""


class ConfiguracaoError(ValueError):
    """Indica que uma configuração obrigatória está ausente ou inválida."""


class GravacaoNaoConfirmadaError(BancoSisplanError):
    """O pedido esperado ainda nao esta gravado, ou sua identificacao diverge."""
