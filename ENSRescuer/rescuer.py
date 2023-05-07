"""
Environment Variables:
- SPONSOR_KEY: Private key of account which will send the ETH.
- HACKED_KEY: Private key of compromised account to execute transaction
- FB_SENDER_KEY: This account is only used for reputation on flashbots and should be empty.
- PROVIDER_URL: HTTP JSON-RPC Ethereum provider URL.
"""

import os
import secrets
from typing import TypedDict
from ast import literal_eval
from uuid import uuid4
from eth_account.account import Account
from eth_account.signers.local import LocalAccount
from flashbots import flashbot
from web3 import Web3, HTTPProvider
from web3.exceptions import TransactionNotFound
from web3.types import TxParams
import json
import argparse, os, json, math, requests

env = os.environ.get

ERC721Abi = '''[{
  "constant": true,
  "inputs": [{"internalType": "address", "name": "owner", "type": "address"}, {
    "internalType": "address",
    "name": "operator",
    "type": "address"
  }],
  "name": "isApprovedForAll",
  "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
  "payable": false,
  "stateMutability": "view",
  "type": "function"
}, {
  "constant": false,
  "inputs": [{"internalType": "address", "name": "to", "type": "address"}, {
    "internalType": "bool",
    "name": "approved",
    "type": "bool"
  }],
  "name": "setApprovalForAll",
  "outputs": [],
  "payable": false,
  "stateMutability": "nonpayable",
  "type": "function"
}, {
  "inputs": [{"internalType": "address", "name": "from", "type": "address"}, {
    "internalType": "address",
    "name": "to",
    "type": "address"
  }, {"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
  "name": "safeTransferFrom",
  "outputs": [],
  "stateMutability": "nonpayable",
  "type": "function"
}, {
  "inputs": [{"internalType": "address", "name": "from", "type": "address"}, {
    "internalType": "address",
    "name": "to",
    "type": "address"
  }, {"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
  "name": "transferFrom",
  "outputs": [],
  "stateMutability": "nonpayable",
  "type": "function"
}]'''

class ENSRescue:
    def __init__(self, args):

        # names.txt containing the tokenIds to rescue
        self.USE_GOERLI = False
        self.CHAIN_ID = 5 if self.USE_GOERLI else 1

        self.w3 = Web3(HTTPProvider(env("PROVIDER_URL")))
        
        # sponsor account, first tx in the bundle
        self.sponsor : LocalAccount = Account.from_key(env("SPONSOR_KEY"))
        # hacked account
        self.hacked: LocalAccount = Account.from_key(env("HACKED_KEY"))
        self.signer: LocalAccount = Account.from_key(env("FB_SIGNER_KEY"))

        # self.w3.eth.default_account = self.hacked.address
        # baseFee at time of execution?
        self.blocks = args.blocks # number of blocks in the future to broadcast for.
        self.erc721_address = self.w3.toChecksumAddress(args.erc721_address) # 0x57f1887a8bf19b14fc0df6fd9b2acc9af147ea85
        self.block_fees = self.w3.eth.fee_history(1, 'latest')
        self.base_fee = self.block_fees["baseFeePerGas"][1]
        self.max_base_fee = self.getMaxBaseFeeInFutureBlock(self.blocks) + Web3.fromWei(self.base_fee, 'gwei')
        self.base_tip = args.base_tip # 2 gwei

        self.names_file = args.names_file
        self.set_approval = args.set_approval
        self.send_to = self.w3.toChecksumAddress(args.send_to) if args.send_to else None

        self.ERC721 = self.w3.eth.contract(
            address = self.erc721_address, 
            abi=ERC721Abi
            )

        if self.USE_GOERLI:
            flashbot(self.w3, self.signer, "https://relay-goerli.flashbots.net")
        else:
            flashbot(self.w3, self.signer)

    # sponsor account send eth to 
    def create_sponsor_account_tx(self, amount):
        nonce = self.w3.eth.get_transaction_count(self.sponsor.address)
        tx: TxParams = {
            "to": self.hacked.address,
            "value": amount,
            "gas": 21000,
            "maxFeePerGas": Web3.toWei(self.max_base_fee, "gwei"), # get the max for in 10 blocks.
            "maxPriorityFeePerGas": Web3.toWei(self.base_tip, "gwei"), 
            "nonce": nonce,
            "chainId": self.CHAIN_ID,
            "type": 2,
        }
        tx_signed = self.sponsor.sign_transaction(tx)
        bundle_tx = {"signed_transaction": tx_signed.rawTransaction}
        return bundle_tx

    def create_signed_transfer(self, token, nonce):

        estimate = self.ERC721.functions.transferFrom(self.hacked.address, self.send_to, int(token)).estimateGas()

        tx: TxParams = {
            "to": self.send_to,
            "data": self.transfer_from_calldata(token),
            "gas": estimate,
            "maxFeePerGas": Web3.toWei(self.max_base_fee, "gwei"), # get the max for in 10 blocks.
            "maxPriorityFeePerGas": Web3.toWei(self.base_tip, "gwei"), 
            "nonce": nonce,
            "chainId": self.CHAIN_ID,
            "type": 2,
        }
        tx_signed = self.hacked.sign_transaction(tx)
        bundle_tx = {"signed_transaction": tx_signed.rawTransaction}
        return bundle_tx
    
    def create_signed_set_approval(self):
        nonce = self.w3.eth.get_transaction_count(self.hacked.address)
        estimate = self.ERC721.functions.setApprovalForAll(self.send_to, True).estimateGas()
        print(f"+ Estimated setApprovalForAll Gas units: {estimate}")

        tx: TxParams = {
            "to": self.erc721_address,
            "data": self.set_approval_calldata(self.hacked.address, self.send_to),
            "gas": estimate,
            "maxFeePerGas": Web3.toWei(self.max_base_fee, "gwei"), # get the max for in 10 blocks.
            "maxPriorityFeePerGas": Web3.toWei(self.base_tip, "gwei"), 
            "nonce": nonce,
            "chainId": self.CHAIN_ID,
            "type": 2,
        }

        tx_signed = self.hacked.sign_transaction(tx)
        bundle_tx = {"signed_transaction": tx_signed.rawTransaction}
        return bundle_tx

    def transfer_from_calldata(self, token):
        call_data = self.ERC721.encodeABI(fn_name="transferFrom", args=[self.hacked.address, self.send_to, int(token)])
        return call_data
    
    # instead of doing transfer do setApprovalForAll to the send_to address
    def set_approval_calldata(self, from_acct, to_acct):
        call_data = self.ERC721.encodeABI(fn_name="setApprovalForAll", args=[to_acct, True])
        return call_data
    
    def load_names(self):
        if self.names_file:
            with open(self.names_file, 'r') as f:
                return f.read().splitlines()
        else:
            print("- No names file specified")
            exit(1)

    def getMaxBaseFeeInFutureBlock(self, blocks_in_the_future):
        max_expansion = 0.125  # Maximum expansion per block (12.5% increase)
        max_fee = 0
        for _ in range(blocks_in_the_future):
            max_fee += math.ceil(Web3.fromWei(self.base_fee, 'gwei')) * max_expansion
        return math.ceil(max_fee)

    def build_approval_bundle(self):
        self.w3.eth.default_account = self.hacked.address
        
        estimate = self.ERC721.functions.setApprovalForAll(self.send_to, True).estimateGas()
        gas_total = estimate * math.floor(Web3.toWei(self.max_base_fee, "gwei") + Web3.toWei(self.base_tip, "gwei"))
        print(f"+ Estimated cost setApprovalForAll: {Web3.fromWei(gas_total, 'ether')} ETH")

        bundle = []
        bundle.append(self.create_sponsor_account_tx(gas_total))
        bundle.append(self.create_signed_set_approval())
        print(f"Bundle : {bundle}")
        return bundle

    def main(self) -> None:

        if not self.send_to:
            print("- No send_to address specified, please specify one with --send_to")
            exit(1)

        print(f"hacked address: {self.hacked.address}")
        print(f"Receiver address: {self.send_to}")
        print(f"Sponsor address: {self.sponsor.address}")

        print(
            f"Hacked account balance: {Web3.fromWei(self.w3.eth.get_balance(self.hacked.address), 'ether')} ETH"
        )
        print(
            f"Sponsor account balance: {Web3.fromWei(self.w3.eth.get_balance(self.sponsor.address), 'ether')} ETH"
        )
        print(f"Current Base fee: WEI {self.base_fee} GWEI {Web3.fromWei(self.base_fee, 'gwei')}")
        print(f"Max base fee in {self.blocks} blocks: {self.max_base_fee} GWEI")


        if self.set_approval:
            print(f"+ Setting approval for all to {self.send_to} from {self.hacked.address}")
            bundle = self.build_approval_bundle()
        else:
            names = self.load_names()
            # build bundle out of loaded names/tokenIds
            # not finished

        # keep trying to send bundle until it gets mined
        block = self.w3.eth.block_number
        while (block < block + self.blocks):
            # block = self.w3.eth.block_number
            print(f"Simulating on block {block}")
            # simulate bundle on current block
            try:
                self.w3.flashbots.simulate(bundle, block)
                print("Simulation successful.")
            except Exception as e:
                print("Simulation error", e)
                return
            
            # return 
            # send bundle targeting next block
            print(f"Sending bundle targeting block {block+1}")
            replacement_uuid = str(uuid4())
            print(f"replacementUuid {replacement_uuid}")
            send_result = self.w3.flashbots.send_bundle(
                bundle,
                target_block_number=block + 1,
                opts={"replacementUuid": replacement_uuid},
            )
            print("bundleHash", self.w3.toHex(send_result.bundle_hash()))

            send_result.wait()
            try:
                receipts = send_result.receipts()
                print(f"\nBundle was mined in block {receipts[0].blockNumber}\a")
                break
            except TransactionNotFound:
                print(f"Bundle not found in block {block+1}")
            
            block += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ENSRescue - lcfr.eth (6/22)\n")
    parser.add_argument("--set-approval", dest="set_approval", action="store_true", 
                        help="Set approval for ENSRegistrar to spend tokens.",
                        default=True)
    
    parser.add_argument("--names-file", dest="names_file", type=str,
                        help="File path name of list of names to rescue.",
                        default="names.txt")
    # add arg for address to send to
    parser.add_argument("--send-to", dest="send_to", type=str, 
                        help="Address to send rescued tokens to.",
                        default=None)
    
    parser.add_argument("--base-tip", dest="base_tip", type=float,
                        help="Base tip in GWEI - default is 1.5gwei, you can try to set this lower to save on total cost",
                        default=20)
    
    parser.add_argument("--blocks", dest="blocks", type=int,
                        help="Number of blocks to try to broadcast for",
                        default=5)
    
    parser.add_argument("--erc721-address", dest="erc721_address", type=str,
                        help="Address of ERC721 contract to rescue from.",
                        default="0x57f1887a8BF19b14fC0dF6Fd9B2acc9Af147eA85")

    args = parser.parse_args()
    x = ENSRescue(args)
    x.main()
