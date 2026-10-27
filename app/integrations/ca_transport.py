"""Bundled into Dify nodes: optional inline PEM trust without temporary files."""
from contextlib import contextmanager


def validate_server(server):
    from urllib.parse import urlsplit
    parsed=urlsplit(server)
    if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or '..' in parsed.path
            or any(c.isspace() for c in server)):
        raise ValueError('TABLEAU_SERVER_URL must be a trusted HTTPS server URL without credentials/query/fragment')
    return server.rstrip('/')


@contextmanager
def tableau_transport(ca_bundle=''):
    import requests
    value=ca_bundle.strip()
    if '-----BEGIN CERTIFICATE-----' not in value:
        # Retain compatibility with older sandbox-local path configurations.
        import os
        if value and (not os.path.isabs(value) or '\r' in value or '\n' in value):
            raise ValueError('Provide PEM CA certificate text or an absolute Linux CA path')
        yield requests, {'verify':value or True}
        return
    import ssl
    from requests.adapters import HTTPAdapter
    if len(value)>200000 or 'PRIVATE KEY' in value:
        raise ValueError('Provide only CA certificates within the 200,000-character limit')
    # Support pasted multiline PEM and values containing literal escaped newlines.
    value=value.replace('\\r\\n','\n').replace('\\n','\n')
    context=ssl.create_default_context()
    try:
        context.load_verify_locations(cadata=value)
    except (ssl.SSLError, ValueError):
        raise ValueError('Invalid PEM CA certificate bundle') from None

    class CAAdapter(HTTPAdapter):
        def build_connection_pool_key_attributes(self, request, verify, cert=None):
            # Requests >=2.32 also sets a per-request SSL context; override it explicitly.
            host, kwargs=super().build_connection_pool_key_attributes(request,verify,cert)
            kwargs['ssl_context']=context
            return host, kwargs

        def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
            kwargs['ssl_context']=context
            return super().init_poolmanager(connections,maxsize,block=block,**kwargs)

        def proxy_manager_for(self, proxy, **kwargs):
            kwargs['ssl_context']=context
            # HTTPS proxies also need corporate trust for their outer TLS connection.
            if proxy.lower().startswith('https://'):
                kwargs['proxy_ssl_context']=context
            return super().proxy_manager_for(proxy,**kwargs)

    with requests.Session() as session:
        session.mount('https://',CAAdapter())
        yield session, {'verify':True}
