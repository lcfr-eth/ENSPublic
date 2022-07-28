#
# ENS Flashbots Rescue script (sponsored transaction)
# https://twitter.com/nicksdjohnson/status/1527065045678452736
#
# can be used to rescue a single name or provide a list of up to 28 names
# to rescue in a single transaction.

# lcfr.eth

from web3 import Web3, HTTPProvider
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3.middleware import construct_sign_and_send_raw_middleware
from web3.middleware import geth_poa_middleware
from flashbots import flashbot
from ast import literal_eval

import argparse, os, json, math

class ENSRescue:
    def __init__(self, args):
        self.nonce = None
        self.test_net = args.test_net

        self.target = args.target_name
        self.basefee_premium = 1.12 # 12% baseFee adjustment
        self.base_tip = args.base_tip
        self.last_sent_block = None
        self.rescuer_key = args.rescuer_key
        self.hacked_key = args.hacked_key
        self.names_file = args.names_file
        self.provider = os.getenv("NODE")
        self.rescuer_account = args.rescuer_account
        # Account with funds for the rescue operation

        self.ETH_ACCOUNT: LocalAccount = Account.from_key(self.rescuer_key)
        self.HACK_ACCOUNT: LocalAccount = Account.from_key(self.hacked_key)


        self.ENS_BASE_REGISTRAR = "0x57f1887a8bf19b14fc0df6fd9b2acc9af147ea85"

        if self.test_net:
            os.environ["FLASHBOTS_HTTP_PROVIDER_URI"] = "https://relay-goerli.flashbots.net"
            self.provider = f"https://goerli.infura.io/v3/yourkeyherelol" #goerli
            print("[+] testnet enabled, connected to goerli infura node.")
            self.chainID = 5

        if not self.provider:
            exit("[-] export provider URL in NODE env variable. Local or Infura or enable testnet mode.")

        self.w3 = Web3(HTTPProvider(self.provider))
        self.w3.eth.default_account = self.ETH_ACCOUNT.address

        if self.test_net:
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            self.w3.middleware_onion.add(construct_sign_and_send_raw_middleware(self.ETH_ACCOUNT))

        self.br_abi_json = json.loads(open('./abi/' + self.ENS_BASE_REGISTRAR + '.json', 'r').read())

        self.ENS_REGISTRAR = self.w3.eth.contract(
            address=self.w3.toChecksumAddress(self.ENS_BASE_REGISTRAR),
            abi=self.br_abi_json
        )

        flashbot(self.w3, self.ETH_ACCOUNT)
        self.flashbots = self.w3.flashbots

    def derive_token_from_name(self, name):
        return literal_eval(Web3.keccak(text=name).hex())

    def transfer_from_call_data(self, from_acct, to_acct, token):
        call_data = self.ENS_REGISTRAR.encodeABI(fn_name="transferFrom", args=[from_acct, to_acct, token])
        return call_data

    def get_miner_calldata(self, price):
        miner_abi = json.loads(open('./abi/0xfee1708400f01f2bb8848ef397c1a2f4c25c910b.json', 'r').read())
        miner_contract = self.w3.eth.contract(
            address=self.w3.toChecksumAddress("0xfee1708400f01f2bb8848ef397c1a2f4c25c910b"),
            abi=miner_abi
        )
        call_data_miner = miner_contract.encodeABI(fn_name="payMiner", args=[self.w3.toWei(price, "gwei")])
        return call_data_miner

    def blank_tx(self):
        tx = {
            "signer": self.HACK_ACCOUNT,
             "transaction": {
                'chainId': self.chainID,
                'nonce': 0,
                "maxFeePerGas": 0,
                "maxPriorityFeePerGas": 0,
                'gas': 0,  
                'to': self.w3.toChecksumAddress(self.ENS_BASE_REGISTRAR), # change to ENS address
                "data": "",
                },
            }
        return tx

    def blank_miner_tx(self):
        miner_pay_tx = {
            "signer": self.ETH_ACCOUNT,
            "transaction": {
                'chainId': self.chainID,
                'nonce': 0,
                "maxFeePerGas": 0,
                "maxPriorityFeePerGas": 0,
                'to': self.w3.toChecksumAddress('0xfee1708400f01f2bb8848ef397c1a2f4c25c910b'),
            },
        }
        return miner_pay_tx


    def build_bundle(self, names):
        bundle_txs      = []
        rescue_tx_cnt   = 0
        hack_tx_cnt     = 0
        total_gas_cost  = 0
        estimate        = 0

        nonce_hack = self.w3.eth.getTransactionCount(self.HACK_ACCOUNT.address)
        nonce_rescue = self.w3.eth.getTransactionCount(self.ETH_ACCOUNT.address)

        if len(names) > 28:
            print(". Bundle can only hold 28 name transactions and found > 28 Names")
            return

        # loop names and do estimateGas() on transferFrom method to get the total gas cost we need to send the account.
        self.w3.eth.default_account = self.HACK_ACCOUNT.address
        for idx, name in enumerate(names):
            estimate = self.ENS_REGISTRAR.functions.transferFrom(self.HACK_ACCOUNT.address, self.ETH_ACCOUNT.address, name).estimateGas()
            base_fee = self.w3.eth.fee_history(1, 'latest')
            gas_total = estimate * math.floor(base_fee["baseFeePerGas"][1] * self.basefee_premium)
            total_gas_cost += gas_total

        base_fee = self.w3.eth.fee_history(1, 'latest')
        fund_tx = self.blank_miner_tx()

        fund_tx["signer"] = self.ETH_ACCOUNT
        fund_tx["transaction"]["nonce"] = nonce_rescue
        fund_tx["transaction"]["to"] = self.w3.toChecksumAddress(self.HACK_ACCOUNT.address)
        fund_tx["transaction"]["from"] = self.w3.toChecksumAddress(self.ETH_ACCOUNT.address)
        fund_tx["transaction"]["maxFeePerGas"] = math.floor(base_fee["baseFeePerGas"][1] * self.basefee_premium)
        fund_tx["transaction"]["gas"] = 21000
        fund_tx["transaction"]["value"] = total_gas_cost
        bundle_txs.append(fund_tx)
        rescue_tx_cnt += 1

        for idx, name in enumerate(names):
            base_fee = self.w3.eth.fee_history(1, 'latest')
            rescue_tx = self.blank_tx()
            rescue_tx["transaction"]["nonce"] = nonce_hack + hack_tx_cnt
            rescue_tx["transaction"]["gas"] = estimate
            rescue_tx["transaction"]["maxFeePerGas"] = math.floor(base_fee["baseFeePerGas"][1] * self.basefee_premium)
            rescue_tx["transaction"]["data"] = self.transfer_from_call_data(self.HACK_ACCOUNT.address, self.rescuer_account, name)
            bundle_txs.append(rescue_tx)
            hack_tx_cnt += 1

        miner_tx = self.blank_miner_tx()
        base_fee = self.w3.eth.fee_history(1, 'latest')
        miner_tx["transaction"]["maxFeePerGas"] = math.floor(base_fee["baseFeePerGas"][1] * self.basefee_premium)
        miner_tx["transaction"]["nonce"] = nonce_rescue + rescue_tx_cnt

        value = self.base_tip * len(names)  # self.base_tip 1.5 Gwei * Names = 1.5Gwei per name as tip.
        miner_tx["transaction"]["data"] = self.get_miner_calldata(value)
        miner_tx["transaction"]["value"] = self.w3.toWei(value, "gwei")

        bundle_txs.append(miner_tx)
        return bundle_txs

    def simulate_tx(self, bundle):
        result = self.flashbots.simulate(bundle, block_tag=self.w3.eth.block_number)
        if "error" in result["results"][0]:
            print(result["results"][0])
            exit(f"[-] {result['results'][0]['error']} - check tx and try again.")
        return

    def send_and_wait_flashbots(self, bundle):
        self.simulate_tx(bundle)
        block_number = self.w3.eth.blockNumber
        if self.last_sent_block == block_number:
            return False

        result = self.flashbots.send_bundle(bundle, target_block_number=block_number + 1)
        self.last_sent_block = block_number
        print(f"[+] Bundle broad casted at block {block_number}\n")
        try:
            result.wait()
            receipts = result.receipts()
            print(receipts)
            print(f"[+] Transaction confirmed at block {self.w3.eth.block_number} [flashbots]")
            return True
        except Exception as exception:
            return False

    def rescue(self, names):
        confirmed = None

        while not confirmed:
            rescue_bundle = self.build_bundle(names)
            confirmed = self.send_and_wait_flashbots(rescue_bundle)
        return

    def main(self):
        names = []
        print(f"[+] rescuing names from: {self.HACK_ACCOUNT.address}.")
        if not self.rescuer_account:
            self.rescuer_account = self.ETH_ACCOUNT.address

        print(f"[+] sending rescued names to: {self.rescuer_account}.")

        if self.names_file:
            name_list = open("./"+self.names_file, 'r').read()
            temp = name_list.split("\n")
            for name in temp:
                if name == "":
                    continue
                names.append(self.derive_token_from_name(name))

        if self.target:
            print(f"[+] Rescuing {self.target}!")
            token_id = self.derive_token_from_name(self.target)
            print(f"[+] token_id of {self.target}.eth : {token_id}")
            names.append(token_id)

        if len(names) > 0:
            #print("doing rescue lol")
            self.rescue(names)
        else:
            exit("[-] No names or file-path of names provided to rescue!")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="ENSRescue - lcfr.eth (6/22)\n")

    parser.add_argument("--name", dest="target_name", type=str,
                        help="Target ENS name to purchase. or use --names-file for file/list of names.",
                        default=None)

    parser.add_argument("--hacked-key", dest="hacked_key",  type=str,
                        help="Private Key of the compromised wallet.",
                        default=False, required=True)

    parser.add_argument("--rescuer-key", dest="rescuer_key", type=str,
                        help="Private key of uncompromised wallet with funds to pay for the rescue.",
                        default=None, required=True)

    parser.add_argument("--rescue-account", dest="rescuer_account", type=str,
                        help="Address where to send rescued names. Does not need to be the address of --rescuer-key.",
                        default=None)

    parser.add_argument("--names-file", dest="names_file", type=str,
                        help="File path name of list of names to rescue.",
                        default=None)

    parser.add_argument("--basetip", dest="base_tip", type=float,
                        help="Base tip in GWEI - default is 1.5gwei, you can try to set this lower to save on total cost",
                        default=1.5)

    parser.add_argument("--testnet", dest="test_net", action='store_true',
                        help="Enable Testnet",
                        default=False)

    args = parser.parse_args()
    x = ENSRescue(args)
    x.main()
