import ssl
import unittest

from dunkin_compare.tls import verified_context


class TrustTests(unittest.TestCase):
    def test_public_roots_are_loaded_without_disabling_verification(self):
        context=verified_context()
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreater(context.cert_store_stats()['x509_ca'],0)
        self.assertGreaterEqual(context.cert_store_stats()['x509_ca'],ssl.create_default_context().cert_store_stats()['x509_ca'])
