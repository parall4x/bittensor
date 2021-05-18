# The MIT License (MIT)
# Copyright © 2021 Yuma Rao

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated 
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, 
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of 
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL 
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION 
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
# DEALINGS IN THE SOFTWARE.
import argparse
import random

from munch import Munch
from typing import List, Tuple, Optional

import bittensor
import bittensor.utils.networking as net
from substrateinterface import SubstrateInterface

from bittensor.utils.balance import Balance

from loguru import logger

logger = logger.opt(colors=True)


def create(config: 'Munch' = None, network=None, endpoint=None):
    subtensor_factory = SubtensorClientFactory(interface_factory=SubtensorInterfaceFactory(SubtensorEndpointFactory()))

    if config:
        return subtensor_factory.create_by_config(config)
    elif network:
        return subtensor_factory.create_by_network(network)
    elif endpoint:
        return subtensor_factory.create_by_endpoint(endpoint)
    else:
        return subtensor_factory.create_default()


class SubtensorClient:
    """
    Handles interactions with the subtensor chain.
    """
    custom_type_registry = {
        "runtime_id": 2,
        "types": {
            "NeuronMetadataOf": {
                "type": "struct",
                "type_mapping": [["ip", "u128"], ["port", "u16"], ["ip_type", "u8"], ["uid", "u64"], ["modality", "u8"],
                                 ["hotkey", "AccountId"], ["coldkey", "AccountId"]]
            }
        }
    }


    @staticmethod
    def add_args(parser: argparse.ArgumentParser):
        parser.add_argument('--subtensor.network', default='kusanagi', type=str,
                            help='''The subtensor network flag. The likely choices are:
                                    -- akira (testing network)
                                    -- kusanagi (main network)
                                If this option is set it overloads subtensor.chain_endpoint with 
                                an entry point node from that network.
                                ''')
        parser.add_argument('--subtensor.chain_endpoint', default=None, type=str,
                            help='''The subtensor endpoint flag. If set, overrides the --network flag.
                                ''')

    @staticmethod
    def default_config() -> Munch:
        # Parses and returns a config Munch for this object.
        parser = argparse.ArgumentParser()
        SubtensorClient.add_args(parser)
        config = bittensor.config.Config.to_config(parser)
        return config


    def __init__(self, interface : 'SubstrateInterface'):
        self.substrate = interface


    def is_subscribed(self, wallet: 'bittensor.wallet.Wallet', ip: str, port: int, modality: int) -> bool:
        r""" Returns true if the bittensor endpoint is already subscribed with the wallet and metadata.
        Args:
            wallet (bittensor.wallet.Wallet):
                bittensor wallet object.
            ip (str):
                endpoint host port i.e. 192.122.31.4
            port (int):
                endpoint port number i.e. 9221
            modality (int):
                int encoded endpoint modality i.e 0 for TEXT
            coldkeypub (str):
                string encoded coldekey pub.
        """

        uid = self.get_uid_for_pubkey(wallet.hotkey.public_key)
        if uid is None:
            return False

        neuron = self.get_neuron_for_uid(uid)
        if neuron['ip'] == net.ip_to_int(ip) and neuron['port'] == port:
            return True
        else:
            return False

    def subscribe(
            self,
            wallet: 'bittensor.wallet.Wallet',
            ip: str,
            port: int,
            modality: int,
            wait_for_inclusion: bool = False,
            wait_for_finalization=True,
            timeout: int = 3 * bittensor.__blocktime__,
    ) -> bool:
        r""" Subscribes an bittensor endpoint to the substensor chain.
        Args:
            wallet (bittensor.wallet.Wallet):
                bittensor wallet object.
            ip (str):
                endpoint host port i.e. 192.122.31.4
            port (int):
                endpoint port number i.e. 9221
            modality (int):
                int encoded endpoint modality i.e 0 for TEXT
            wait_for_inclusion (bool):
                if set, waits for the extrinsic to enter a block before returning true, 
                or returns false if the extrinsic fails to enter the block within the timeout.   
            wait_for_finalization (bool):
                if set, waits for the extrinsic to be finalized on the chain before returning true,
                or returns false if the extrinsic fails to be finalized within the timeout.
            timeout (int):
                time that this call waits for either finalization of inclusion.
        Returns:
            success (bool):
                flag is true if extrinsic was finalized or uncluded in the block. 
                If we did not wait for finalization / inclusion, the response is true.
        """

        if self.is_subscribed(wallet, ip, port, modality):
            logger.success(
                "Already subscribed with:\n<cyan>[\n  ip: {},\n  port: {},\n  modality: {},\n  hotkey: {},\n  coldkey: {}\n]</cyan>".format(
                    ip, port, modality, wallet.hotkey.public_key, wallet.coldkeypub))
            return True

        ip_as_int = net.ip_to_int(ip)
        params = {
            'ip': ip_as_int,
            'port': port,
            'ip_type': 4,
            'modality': modality,
            'coldkey': wallet.coldkeypub,
        }
        call = self.substrate.compose_call(
            call_module='SubtensorModule',
            call_function='subscribe',
            call_params=params
        )
        # TODO (const): hotkey should be an argument here not assumed. Either that or the coldkey pub should also be assumed.
        extrinsic = self.substrate.create_signed_extrinsic(call=call, keypair=wallet.hotkey)
        result = self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion, wait_for_finalization).is_success
        if result:
            logger.success(
                "Successfully subscribed with:\n<cyan>[\n  ip: {},\n  port: {},\n  modality: {},\n  hotkey: {},\n  coldkey: {}\n]</cyan>".format(
                    ip, port, modality, wallet.hotkey.public_key, wallet.coldkeypub))
        else:
            logger.error("Failed to subscribe")
        return result

    def add_stake(
            self,
            wallet: 'bittensor.wallet.Wallet',
            amount: Balance,
            hotkey_id: int,
            wait_for_inclusion: bool = False,
            wait_for_finalization: bool = False,
            timeout: int = 3 * bittensor.__blocktime__,
    ) -> bool:
        r""" Adds the specified amount of stake to passed hotkey uid.
        Args:
            wallet (bittensor.wallet.Wallet):
                bittensor wallet object.
            amount (bittensor.utils.balance.Balance):
                amount to stake as bittensor balance
            hotkey_id (int):
                uid of hotkey to stake into.
            wait_for_inclusion (bool):
                if set, waits for the extrinsic to enter a block before returning true, 
                or returns false if the extrinsic fails to enter the block within the timeout.   
            wait_for_finalization (bool):
                if set, waits for the extrinsic to be finalized on the chain before returning true,
                or returns false if the extrinsic fails to be finalized within the timeout.
            timeout (int):
                time that this call waits for either finalization of inclusion.
        Returns:
            success (bool):
                flag is true if extrinsic was finalized or uncluded in the block. 
                If we did not wait for finalization / inclusion, the response is true.
        """
        call = self.substrate.compose_call(
            call_module='SubtensorModule',
            call_function='add_stake',
            call_params={
                'hotkey': hotkey_id,
                'ammount_staked': amount.rao
            }
        )
        extrinsic = self.substrate.create_signed_extrinsic(call=call, keypair=wallet.coldkey)
        return self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion, wait_for_finalization).is_success

    def transfer(
            self,
            wallet: 'bittensor.wallet.Wallet',
            dest: str,
            amount: Balance,
            wait_for_inclusion: bool = False,
            wait_for_finalization: bool = False,
            timeout: int = 3 * bittensor.__blocktime__,
    ) -> bool:
        r""" Transfers funds from this wallet to the destination public key address
        Args:
            wallet (bittensor.wallet.Wallet):
                bittensor wallet object.
            dest (str):
                destination public key address of reciever. 
            amount (bittensor.utils.balance.Balance):
                amount to stake as bittensor balance
            wait_for_inclusion (bool):
                if set, waits for the extrinsic to enter a block before returning true, 
                or returns false if the extrinsic fails to enter the block within the timeout.   
            wait_for_finalization (bool):
                if set, waits for the extrinsic to be finalized on the chain before returning true,
                or returns false if the extrinsic fails to be finalized within the timeout.
            timeout (int):
                time that this call waits for either finalization of inclusion.
        Returns:
            success (bool):
                flag is true if extrinsic was finalized or uncluded in the block. 
                If we did not wait for finalization / inclusion, the response is true.
        """
        call = self.substrate.compose_call(
            call_module='Balances',
            call_function='transfer',
            call_params={
                'dest': dest,
                'value': amount.rao
            }
        )
        extrinsic = self.substrate.create_signed_extrinsic(call=call, keypair=wallet.coldkey)
        return self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion, wait_for_finalization).is_success

    def unstake(
            self,
            wallet: 'bittensor.wallet.Wallet',
            amount: Balance,
            hotkey_id: int,
            wait_for_inclusion: bool = False,
            wait_for_finalization: bool = False,
            timeout: int = 3 * bittensor.__blocktime__,
    ) -> bool:
        r""" Removes stake into the wallet coldkey from the specified hotkey uid.
        Args:
            wallet (bittensor.wallet.Wallet):
                bittensor wallet object.
            amount (bittensor.utils.balance.Balance):
                amount to stake as bittensor balance
            hotkey_id (int):
                uid of hotkey to unstake from.
            wait_for_inclusion (bool):
                if set, waits for the extrinsic to enter a block before returning true, 
                or returns false if the extrinsic fails to enter the block within the timeout.   
            wait_for_finalization (bool):
                if set, waits for the extrinsic to be finalized on the chain before returning true,
                or returns false if the extrinsic fails to be finalized within the timeout.
            timeout (int):
                time that this call waits for either finalization of inclusion.
        Returns:
            success (bool):
                flag is true if extrinsic was finalized or uncluded in the block. 
                If we did not wait for finalization / inclusion, the response is true.
        """
        call = self.substrate.compose_call(
            call_module='SubtensorModule',
            call_function='remove_stake',
            call_params={'ammount_unstaked': amount.rao, 'hotkey': hotkey_id}
        )
        extrinsic = self.substrate.create_signed_extrinsic(call=call, keypair=wallet.coldkey)
        return self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion, wait_for_finalization).is_success

    def set_weights(
            self,
            wallet: 'bittensor.wallet.Wallet',
            destinations,
            values,
            wait_for_inclusion: bool = False,
            wait_for_finalization: bool = False,
            timeout: int = 3 * bittensor.__blocktime__
    ) -> bool:
        r""" Sets the given weights and values on chain for wallet hotkey account.
        Args:
            wallet (bittensor.wallet.Wallet):
                bittensor wallet object.
            destinations (List[int]):
                uint64 uids of destination neurons.
            values (List[int]):
                u32 max encoded floating point weights.
            wait_for_inclusion (bool):
                if set, waits for the extrinsic to enter a block before returning true, 
                or returns false if the extrinsic fails to enter the block within the timeout.
            wait_for_finalization (bool):
                if set, waits for the extrinsic to be finalized on the chain before returning true,
                or returns false if the extrinsic fails to be finalized within the timeout.
            timeout (int):
                time that this call waits for either finalization of inclusion.
        Returns:
            success (bool):
                flag is true if extrinsic was finalized or uncluded in the block. 
                If we did not wait for finalization / inclusion, the response is true.
        """
        call = self.substrate.compose_call(
            call_module='SubtensorModule',
            call_function='set_weights',
            call_params={'dests': destinations, 'weights': values}
        )
        extrinsic = self.substrate.create_signed_extrinsic(call=call, keypair=wallet.hotkey)
        return self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion=wait_for_inclusion,
                                               wait_for_finalization=wait_for_finalization).is_success

    def get_balance(self, address: str) -> Balance:
        r""" Returns the token balance for the passed ss58_address address
        Args:
            address (Substrate address format, default = 42):
                ss58 chain address.
        Return:
            balance (bittensor.utils.balance.Balance):
                account balance
        """
        result = self.substrate.get_runtime_state(
            module='System',
            storage_function='Account',
            params=[address],
            block_hash=None
        )
        balance_info = result.get('result')
        if not balance_info:
            return Balance(0)
        balance = balance_info['data']['free']
        return Balance(balance)

    def get_current_block(self) -> int:
        r""" Returns the current block number on the chain.
        Returns:
            block_number (int):
                Current chain blocknumber.
        """
        return self.substrate.get_block_number(None)

    def get_block_hash(self, block_nr):
        return self.substrate.get_block_hash(block_nr)

    def get_active(self) -> List[Tuple[str, int]]:
        r""" Returns a list of (public key, uid) pairs one for each active peer on chain.
        Returns:
            active (List[Tuple[str, int]]):
                List of active peers.
        """
        result = self.substrate.iterate_map(
            module='SubtensorModule',
            storage_function='Active',
        )
        return result

    def get_stake(self, hash=None) -> List[Tuple[int, int]]:
        r""" Returns a list of (uid, stake) pairs one for each active peer on chain.
        Returns:
            stake (List[Tuple[int, int]]):
                List of stake values.
        """
        result = self.substrate.iterate_map(
            module='SubtensorModule',
            storage_function='Stake',
            block_hash=hash
        )
        return result

    def get_last_emit(self, hash=None) -> List[Tuple[int, int]]:
        r""" Returns a list of (uid, last emit) pairs for each active peer on chain.
        Returns:
            last_emit (List[Tuple[int, int]]):
                List of last emit values.
        """
        result = self.substrate.iterate_map(
            module='SubtensorModule',
            storage_function='LastEmit',
            block_hash=hash
        )
        return result

    def get_weight_vals(self, hash=None) -> List[Tuple[int, List[int]]]:
        r""" Returns a list of (uid, weight vals) pairs for each active peer on chain.
        Returns:
            weight_vals (List[Tuple[int, List[int]]]):
                List of weight val pairs.
        """
        result = self.substrate.iterate_map(
            module='SubtensorModule',
            storage_function='WeightVals',
            block_hash=hash
        )
        return result

    def get_weight_uids(self, hash=None) -> List[Tuple[int, int]]:
        r""" Returns a list of (uid, weight uids) pairs for each active peer on chain.
        Returns:
            weight_uids (List[Tuple[int, List[int]]]):
                List of weight uid pairs
        """
        result = self.substrate.iterate_map(
            module='SubtensorModule',
            storage_function='WeightUids',
            block_hash=hash
        )
        return result

    def neurons(self, hash=None) -> List[Tuple[int, dict]]:
        r""" Returns a list of neuron from the chain. 
        Returns:
            neuron (List[Tuple[int, dict]]):
                List of neuron objects.
        """
        neurons = self.substrate.iterate_map(
            module='SubtensorModule',
            storage_function='Neurons',
            block_hash=hash
        )
        return neurons



    # def __convert_neuron(self, data) -> dict:
    #
    #     return dict({
    #         'coldkey': data['coldkey'],
    #         'hotkey': data['hotkey'],
    #         'ip_type': int(data['ip_type']),
    #         'ip': int(data['ip']),
    #         'port': int(data['port']),
    #         'modality': int(data['modality']),
    #         'uid': int(data['uid'])
    #     })

    def get_uid_for_pubkey(self, pubkey=str) -> Optional[int]:
        """ Returns the uid of the peer given passed public key string.
        Args:
            pubkey (str):
                String encoded public key.
        Returns:
            uid (int):
                uid of peer with hotkey equal to passed public key.
        """
        result = self.substrate.get_runtime_state(
            module='SubtensorModule',
            storage_function='Active',
            params=[pubkey]
        )

        if result['result'] is None:
            return None
        return int(result['result'])

    def get_neuron_for_uid(self, uid) -> dict:
        """ Returns the neuron metadata of the peer with the passed uid.
        Args:
            uid (int):
                Uid to query for metadata.
        Returns:
            metadata (Dict):
                Dict in list form containing metadata of associated uid.
        """
        result = self.substrate.get_runtime_state(
            module='SubtensorModule',
            storage_function='Neurons',
            params=[uid]
        )
        return result['result']

    def get_stake_for_uid(self, uid) -> Balance:
        r""" Returns the staked token amount of the peer with the passed uid.
        Args:
            uid (int):
                Uid to query for metadata.
        Returns:
            stake (int):
                Amount of staked token.
        """
        stake = self.substrate.get_runtime_state(
            module='SubtensorModule',
            storage_function='Stake',
            params=[uid]
        )
        result = stake['result']
        if not result:
            return Balance(0)
        return Balance(result)

    def weight_uids_for_uid(self, uid) -> List[int]:
        r""" Returns the weight uids of the peer with the passed uid.
        Args:
            uid (int):
                Uid to query for metadata.
        Returns:
            weight_uids (List[int]):
                Weight uids for passed uid.
        """
        result = self.substrate.get_runtime_state(
            module='SubtensorModule',
            storage_function='WeightUids',
            params=[uid]
        )
        return result['result']

    def weight_vals_for_uid(self, uid) -> List[int]:
        r""" Returns the weight vals of the peer with the passed uid.
        Args:
            uid (int):
                Uid to query for metadata.
        Returns:
            weight_vals (List[int]):
                Weight vals for passed uid.
        """
        result = self.substrate.get_runtime_state(
            module='SubtensorModule',
            storage_function='WeightVals',
            params=[uid]
        )
        return result['result']

    def get_last_emit_data_for_uid(self, uid) -> int:
        r""" Returns the last emit of the peer with the passed uid.
        Args:
            uid (int):
                Uid to query for metadata.
        Returns:
            last_emit (int):
                Last emit block numebr
        """
        result = self.substrate.get_runtime_state(
            module='SubtensorModule',
            storage_function='LastEmit',
            params = [uid]
        )
        return result['result']


class SubtensorEndpointFactory:
    def __init__(self):

        self.endpoints = {
            "akira": [
                'ws://fermi.akira.bittensor.com:9944',
                'ws://copernicus.akira.bittensor.com:9944',
                'ws://buys.akira.bittensor.com:9944',
                'ws://nobel.akira.bittensor.com:9944',
                'ws://mendeleev.akira.bittensor.com:9944',
                'ws://rontgen.akira.bittensor.com:9944',
                'ws://feynman.akira.bittensor.com:9944',
                'ws://bunsen.akira.bittensor.com:9944',
                'ws://berkeley.akira.bittensor.com:9944',
                'ws://huygens.akira.bittensor.com:9944',
            ],
            "kusanagi": [
                'ws://fermi.kusanagi.bittensor.com:9944',
                'ws://copernicus.kusanagi.bittensor.com:9944',
                'ws://buys.kusanagi.bittensor.com:9944',
                'ws://nobel.kusanagi.bittensor.com:9944',
                'ws://mendeleev.kusanagi.bittensor.com:9944',
                'ws://rontgen.kusanagi.bittensor.com:9944',
                'ws://feynman.kusanagi.bittensor.com:9944',
                'ws://bunsen.kusanagi.bittensor.com:9944',
                'ws://berkeley.kusanagi.bittensor.com:9944',
                'ws://huygens.kusanagi.bittensor.com:9944',
            ],
            "boltzmann": [
                'ws://feynman.boltzmann.bittensor.com:9944',
            ],
            "local": [
                'ws://127.0.0.1:9944'
            ]}



    def get(self, network, blacklist=None):
        if blacklist is None:
            blacklist = []
        if network not in self.endpoints:
            logger.error("[!] network [{}] not in endpoints list", network)
            return None

        endpoints = self.endpoints[network]
        endpoint_available = [item for item in endpoints if item not in blacklist]
        if len(endpoint_available) == 0:
            return None

        return random.choice(endpoint_available)


class SubtensorInterfaceFactory:
    def __init__(self, endpoint_factory : 'SubtensorEndpointFactory'):
        self.__endpoint_factory = endpoint_factory
        self.__attempted_endpoints = []
        self.__custom_type_registry = {
            "runtime_id": 2,
            "types": {
                "NeuronMetadataOf": {
                    "type": "struct",
                    "type_mapping": [["ip", "u128"], ["port", "u16"], ["ip_type", "u8"], ["uid", "u64"],
                                     ["modality", "u8"], ["hotkey", "AccountId"], ["coldkey", "AccountId"]]
                }
            }
        }


    def get_by_endpoint(self, endpoint : str):
        interface =  self.__get_interface(endpoint)

        # We're not attaching an observer here, because a single endpoint does not have an alternative
        # To reconnect to
        return interface

    def get_by_network(self, network: str):
        endpoint = self.__endpoint_factory.get(network=network)
        interface = self.__get_interface(endpoint)

        return interface

    def __get_interface(self, endpoint):
        interface = SubstrateInterface(
            address_type=42,
            type_registry_preset='substrate-node-template',
            type_registry=self.__custom_type_registry,
            url=endpoint
        )

        return interface

    ''' Error message helper functions '''

    def __display_no_more_endpoints_message(self, network):
        logger.log('USER-CRITICAL', "No more endpoints available for subtensor.network: {}, attempted: {}".format(
            network, self.__attempted_endpoints))

    def __display_timeout_message(self, endpoint):
        logger.log('USER-CRITICAL', "Error while connecting to the chain endpoint {}".format(endpoint))

    def __display_success_message(self, endpoint):
        logger.log('USER-SUCCESS', "Successfully connected to endpoint: {}".format(endpoint))


    def __connection_error_message(self):
            print('''
    Check that your internet connection is working and the chain endpoints are available: {}
    The subtensor.network should likely be one of the following choices:
        -- local - (your locally running node)
        -- akira - (testnet)
        -- kusanagi - (mainnet)
    Or you may set the endpoint manually using the --subtensor.chain_endpoint flag
    To run a local node (See: docs/running_a_validator.md) \n
                                  '''.format(self.__attempted_endpoints))


class SubtensorClientFactory:
    def __init__(self, interface_factory: 'SubtensorInterfaceFactory'):
        self.__interface_factory = interface_factory

    def create_by_config(self, config : 'Munch'):
        if config.subtensor.chain_endpoint:
            return self.create_by_endpoint(config.subtensor.chain_endpoint)
        elif config.subtensor.network:
            return self.create_by_network(config.subtensor.network)
        else:
            logger.error("[!] Invalid subtensor config. chain_endpoint and network not defined")
            return None

    def create_by_network(self, network: str):
        interface =  self.__interface_factory.get_by_network(network)
        return self.__build_client(interface)

    def create_by_endpoint(self, endpoint: str):
        interface =  self.__interface_factory.get_by_endpoint(endpoint)
        return self.__build_client(interface)

    def create_default(self):
        config = SubtensorClient.default_config()
        return self.create_by_config(config)

    def __build_client(self, interface : 'SubstrateInterface'):
        return SubtensorClient(interface)
