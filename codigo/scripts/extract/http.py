"""Sessão TLS com certificados nativos do sistema, sem desativar verificação."""
import ssl

import requests
import truststore


class NativeTLSAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        return super().init_poolmanager(*args, **kwargs)

    def build_connection_pool_key_attributes(self, request, verify, cert=None):
        host, pool = super().build_connection_pool_key_attributes(request, verify, cert)
        if verify is True:
            pool['ssl_context'] = self.poolmanager.connection_pool_kw['ssl_context']
        return host, pool


def criar_sessao_inep() -> requests.Session:
    sessao = requests.Session()
    sessao.mount('https://download.inep.gov.br/', NativeTLSAdapter())
    return sessao
