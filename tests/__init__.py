from simple_settings import settings
import unittest

class BittensorTestCase(unittest.TestCase):
    def getChainEndpoint(self):
        return settings.CHAIN_ENDPOINT
