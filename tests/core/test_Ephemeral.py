# coding=utf-8
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.
from unittest import TestCase
from mock import Mock, mock
from pyqrllib.kyber import Kyber
from pyqrllib.dilithium import Dilithium

from qrl.crypto.xmss import XMSS
from qrl.core import config
from qrl.core.misc import logger
from qrl.core.ChainManager import ChainManager
from qrl.core.Miner import Miner
from qrl.core.Block import Block
from qrl.core.GenesisBlock import GenesisBlock
from qrl.core.State import State
from qrl.core.Transaction import LatticePublicKey
from qrl.generated import qrl_pb2
from tests.misc.helper import set_wallet_dir, get_alice_xmss, get_random_xmss, mocked_genesis, create_ephemeral_channel, \
                              set_data_dir
from tests.misc.EphemeralPayload import EphemeralChannelPayload
from tests.misc.aes import AES

logger.initialize_default()


class TestEphemeral(TestCase):
    def __init__(self, *args, **kwargs):
        super(TestEphemeral, self).__init__(*args, **kwargs)

    def test_init(self):
        # TODO: Not much going on here..
        block = Block()
        self.assertIsNotNone(block)             # just to avoid warnings

    def test_add_4(self):
        with set_data_dir('no_data'):
            with State() as state:
                with set_wallet_dir("test_wallet"):
                    miner = Miner(Mock(), Mock())
                    chain_manager = ChainManager(state)
                    chain_manager.set_miner(miner)

                    alice_xmss = get_alice_xmss()
                    slave_xmss = XMSS(alice_xmss.height, alice_xmss.get_seed())
                    random_xmss1 = get_random_xmss()
                    random_kyber1 = Kyber()
                    random_dilithium1 = Dilithium()
                    random_xmss2 = get_random_xmss()
                    random_kyber2 = Kyber()
                    random_dilithium2 = Dilithium()

                    message = b'Hello World How are you?'
                    prf512_seed = b'10192'

                    with mocked_genesis() as custom_genesis:
                        custom_genesis.genesis_balance.extend(
                            [qrl_pb2.GenesisBalance(address=random_xmss1.get_address(),
                                                    balance=65000000000000000)])
                        custom_genesis.genesis_balance.extend(
                            [qrl_pb2.GenesisBalance(address=random_xmss2.get_address(),
                                                    balance=65000000000000000)])
                        chain_manager.load(custom_genesis)
                        lattice_public_key_txn = LatticePublicKey.create(addr_from=random_xmss1.get_address(),
                                                                         fee=1,
                                                                         kyber_pk=random_kyber1.getPK(),
                                                                         dilithium_pk=random_dilithium1.getPK(),
                                                                         xmss_pk=random_xmss1.pk())
                        lattice_public_key_txn._data.nonce = 1
                        lattice_public_key_txn.sign(random_xmss1)

                        tmp_block1 = Block.create(mining_nonce=10,
                                                  block_number=1,
                                                  prevblock_headerhash=GenesisBlock().headerhash,
                                                  transactions=[lattice_public_key_txn],
                                                  signing_xmss=slave_xmss,
                                                  nonce=1)

                        res = chain_manager.add_block(block=tmp_block1)
                        self.assertTrue(res)

                        # Need to move forward the time to align with block times
                        with mock.patch('qrl.core.misc.ntp.getTime') as time_mock:
                            time_mock.return_value = tmp_block1.timestamp + config.dev.minimum_minting_delay

                            encrypted_eph_message = create_ephemeral_channel(msg_id=lattice_public_key_txn.txhash,
                                                                             ttl=time_mock.return_value,
                                                                             ttr=0,
                                                                             addr_from=random_xmss2.get_address(),
                                                                             kyber_pk=random_kyber2.getPK(),
                                                                             kyber_sk=random_kyber2.getSK(),
                                                                             receiver_kyber_pk=random_kyber1.getPK(),
                                                                             dilithium_pk=random_dilithium2.getPK(),
                                                                             dilithium_sk=random_dilithium2.getSK(),
                                                                             prf512_seed=prf512_seed,
                                                                             data=message,
                                                                             nonce=1)

                            chain_manager.state.update_ephemeral(encrypted_eph_message)
                            eph_metadata = chain_manager.state.get_ephemeral_metadata(lattice_public_key_txn.txhash)

                            # Decrypting Payload

                            encrypted_eph_message = eph_metadata.encrypted_ephemeral_message_list[0]
                            encrypted_payload = encrypted_eph_message.payload

                            random_kyber1.kem_decode(encrypted_eph_message.channel.enc_aes256_symkey)
                            aes_key = bytes(random_kyber1.getMyKey())
                            myAES = AES(aes_key)
                            decrypted_payload = myAES.decrypt(encrypted_payload)
                            ephemeral_channel_payload = EphemeralChannelPayload.from_json(decrypted_payload)

                            self.assertEqual(ephemeral_channel_payload.prf512_seed, b'10192')
                            self.assertEqual(ephemeral_channel_payload.data, b'Hello World How are you?')

                            # TODO (cyyber): Add Ephemeral Testing code using Naive RNG

                            tmp_block2 = Block.create(mining_nonce=15,
                                                      block_number=2,
                                                      prevblock_headerhash=tmp_block1.headerhash,
                                                      transactions=[],
                                                      signing_xmss=slave_xmss,
                                                      nonce=2)

                        res = chain_manager.add_block(block=tmp_block2)
                        self.assertTrue(res)

                        # Need to move forward the time to align with block times
                        with mock.patch('qrl.core.misc.ntp.getTime') as time_mock:
                            time_mock.return_value = tmp_block2.timestamp + config.dev.minimum_minting_delay

                            tmp_block3 = Block.create(mining_nonce=20,
                                                      block_number=3,
                                                      prevblock_headerhash=tmp_block2.headerhash,
                                                      transactions=[],
                                                      signing_xmss=slave_xmss,
                                                      nonce=3)

                        res = chain_manager.add_block(block=tmp_block3)
                        self.assertTrue(res)

                        address_state = chain_manager.state.get_address(random_xmss1.get_address())

                        self.assertEqual(address_state.latticePK_list[0].kyber_pk, lattice_public_key_txn.kyber_pk)
                        self.assertEqual(address_state.latticePK_list[0].dilithium_pk,
                                         lattice_public_key_txn.dilithium_pk)
                        self.assertEqual(address_state.address, lattice_public_key_txn.txfrom)
                        # Need to move forward the time to align with block times
                        with mock.patch('qrl.core.misc.ntp.getTime') as time_mock:
                            time_mock.return_value = tmp_block3.timestamp + config.dev.minimum_minting_delay

                            tmp_block4 = Block.create(mining_nonce=25,
                                                      block_number=4,
                                                      prevblock_headerhash=tmp_block3.headerhash,
                                                      transactions=[],
                                                      signing_xmss=slave_xmss,
                                                      nonce=4)

                        res = chain_manager.add_block(block=tmp_block4)
                        self.assertTrue(res)

                        random_xmss1_state = chain_manager.state._get_address_state(random_xmss1.get_address())

                        self.assertEqual(64999999999999999, random_xmss1_state.balance)
