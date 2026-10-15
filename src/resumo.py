from collections import Counter
from dataclasses import dataclass, field

from src.logs import get_logger

logger = get_logger(__name__)


@dataclass
class ResumoExecucao:
    situacoes: dict[str, str] = field(default_factory=dict)
    importados: set[str] = field(default_factory=set)
    retomados: set[str] = field(default_factory=set)

    def exibir(self) -> None:
        contagem = Counter(self.situacoes.values())
        logger.info_split('RESUMO FINAL — %s pedido(s)', len(self.situacoes))
        logger.info('Já existentes: %s', contagem['existente'])
        logger.info('Importações confirmadas nesta execução: %s', len(self.importados))
        logger.info('Pedidos retomados para impressão: %s', len(self.retomados))
        logger.info('Rejeitados: %s | Falhas: %s', contagem['rejeitado'], contagem['falhou'])
        logger.info('Impressões enviadas ao SumatraPDF: %s', contagem['impressao_enviada'])
        for situacao, titulo in (
            ('gravacao_pendente', 'Gravações não confirmadas'),
            ('impressao_pendente', 'Impressões pendentes'),
            ('impressao_incerta', 'Envios de impressão incertos'),
            ('aguardando', 'Pedidos não processados'),
        ):
            pedidos = [p for p, valor in self.situacoes.items() if valor == situacao]
            logger.info('%s: %s%s', titulo, len(pedidos), f' ({", ".join(pedidos)})' if pedidos else '')
