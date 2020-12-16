from bittensor.subtensor.client import WSClient
from bittensor.subtensor.interface import Keypair
from loguru import logger
import pytest
import asyncio

# logger.remove() # Shut up loguru


@pytest.mark.asyncio
async def test_set_weights():
    socket = "localhost:9944"
    keypair = Keypair.create_from_uri('//Alice')
    client = WSClient(socket, keypair)

    client.connect()

    keypair_extrinsic_signer = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())

    key_1 = Keypair.create_from_mnemonic(Keypair.generate_mnemonic()).public_key
    key_2 = Keypair.create_from_mnemonic(Keypair.generate_mnemonic()).public_key
    keys = [key_1, key_2]

    value_1 = 88
    value_2 = 88875557

    vals = [value_1, value_2]

    await client.is_connected()
    await client.set_weights(keys, vals, keypair_extrinsic_signer, wait_for_inclusion=False)

    await asyncio.sleep(6)

    chain_keys = await client.weight_keys(keypair_extrinsic_signer.public_key)
    chain_vals = await client.weight_vals(keypair_extrinsic_signer.public_key)

    assert keys == chain_keys
    assert vals == chain_vals


