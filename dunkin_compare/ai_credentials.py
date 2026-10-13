"""Read API authentication without writing credentials into application files."""
import os
import sys

SERVICE='DunkinPriceAgent.OpenAI'
ACCOUNT='api-key'


def backend():
    if sys.platform=='darwin':
        from keyring.backends.macOS import Keyring
        return Keyring()
    if os.name=='nt':
        from keyring.backends.Windows import WinVaultKeyring
        return WinVaultKeyring()
    raise RuntimeError('Secure API-key entry is supported on Mac and Windows. On Linux, use OPENAI_API_KEY.')


def get_key():
    key=os.environ.get('OPENAI_API_KEY','').strip()
    if key:
        return key
    try:
        return backend().get_password(SERVICE,ACCOUNT) or ''
    except Exception:
        return ''


def save_key(value):
    if not value.strip():
        raise ValueError('Enter your API key in this app, not in chat.')
    backend().set_password(SERVICE,ACCOUNT,value.strip())
