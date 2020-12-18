from bittensor.subtensor.client import WSClient
from bittensor.subtensor.interface import Keypair
from loguru import logger
import pytest
import asyncio
import unittest

# logger.remove() # Shut up loguru

class testSetWeights(unittest.TestCase):
    client : WSClient

    def setUp(self) -> None:
        socket = "localhost:9944"
        keypair = Keypair.create_from_uri('//Alice')
        self.client = WSClient(socket, keypair)
        self.client.connect()

    def tearDown(self):
        # @todo Implement disconnect method for client
        pass

    def __runtest(self, name):
        # Run the async test
        loop = asyncio.get_event_loop()
        loop.run_until_complete(name)
        loop.close()

    def test_setweights(self):
        self.__runtest(self._test_set_weights())

    async def _test_set_weights(self):
        keypair_extrinsic_signer = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())

        key_1 = Keypair.create_from_mnemonic(Keypair.generate_mnemonic()).public_key
        key_2 = Keypair.create_from_mnemonic(Keypair.generate_mnemonic()).public_key
        keys = [key_1, key_2]

        value_1 = 88
        value_2 = 88875557

        vals = [value_1, value_2]

        await self.client.is_connected()
        await self.client.set_weights(keys, vals, keypair_extrinsic_signer, wait_for_inclusion=False)
        await asyncio.sleep(6)
        await self.client.set_weights(keys, vals, keypair_extrinsic_signer, wait_for_inclusion=False)

        await asyncio.sleep(6)

        chain_keys = await self.client.weight_keys(keypair_extrinsic_signer.public_key)
        chain_vals = await self.client.weight_vals(keypair_extrinsic_signer.public_key)

        assert keys == chain_keys
        assert vals == chain_vals




