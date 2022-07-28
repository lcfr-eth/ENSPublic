
from web3 import Web3, HTTPProvider
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3.middleware import construct_sign_and_send_raw_middleware
from web3.middleware import geth_poa_middleware
from flashbots import flashbot
from ens.auto import ns

import argparse, time, random, os, json, math


class ENSBuy:
    def __init__(self, args):
        self.nonce = None
        self.test_net = args.test_net

        self.target = args.target_name
        self.commitment = args.make_commitment
        self.commit = args.send_commitment
        self.buy_name_salt = args.buy_name
        self.duration = 31556952 * args.duration # 1 year
        self.autopilot = args.autopilot
        self.list_buy = args.list_names
        self.set_avatar_list = args.set_avatar_list # test multicall
        self.basefee_premium = 1.12 # 12-20% baseFee adjustment
        self.base_tip = args.base_tip
        self.last_sent_block = None

        # REQUIRED
        self.p_key = os.getenv("PKEY")
        self.provider = os.getenv("NODE")

        self.ETH_ACCOUNT: LocalAccount = Account.from_key(self.p_key)
        self.ENS_REGISTRAR_CONTROLLER = "0x283af0b28c62c092c9727f1ee09c02ca627eb7f5"
        self.ENS_BASE_REGISTRAR = "0x57f1887a8bf19b14fc0df6fd9b2acc9af147ea85"
        self.ENS_PUBLIC_RESOLVER = "0x4976fb03c32e5b8cfe2b6ccb31c09ba78ebaba41"

        if self.test_net:
            self.ENS_PUBLIC_RESOLVER = "0x4b1488b7a6b320d2d721406204abc3eeaa9ad329"
            os.environ["FLASHBOTS_HTTP_PROVIDER_URI"] = "https://relay-goerli.flashbots.net"
            self.provider = f"https://goerli.infura.io/v3/yourkey" #goerli
            print("[+] testnet enabled, connected to goerli infura node.")
            self.chainID = 5

        if not self.provider:
            exit("[-] export provider URL in NODE env variable. Local or Infura or enable testnet mode.")

        self.w3 = Web3(HTTPProvider(self.provider))
        self.w3.eth.default_account = self.ETH_ACCOUNT.address

        if self.test_net:
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            self.w3.middleware_onion.add(construct_sign_and_send_raw_middleware(self.ETH_ACCOUNT))

        self.rc_abi_json = json.loads(open('./abi/' + self.ENS_REGISTRAR_CONTROLLER + '.json', 'r').read())
        self.br_abi_json = json.loads(open('./abi/' + self.ENS_BASE_REGISTRAR + '.json', 'r').read())
        self.pr_abi_json = json.loads(open('./abi/' + self.ENS_PUBLIC_RESOLVER + '.json', 'r').read())

        self.ENS = self.w3.eth.contract(
            address=self.w3.toChecksumAddress(self.ENS_REGISTRAR_CONTROLLER),
            abi=self.rc_abi_json
        )
        self.ENS_REGISTRAR = self.w3.eth.contract(
            address=self.w3.toChecksumAddress(self.ENS_BASE_REGISTRAR),
            abi=self.br_abi_json
        )
        self.ENS_RESOLVER = self.w3.eth.contract(
            address=self.w3.toChecksumAddress(self.ENS_PUBLIC_RESOLVER),
            abi=self.pr_abi_json
        )
        self.connection = None
        flashbot(self.w3, self.ETH_ACCOUNT)
        self.flashbots = self.w3.flashbots

    def make_commitment(self, name):
        print("[+] Generating commitment for %s" % name)
        salt = self.w3.toHex(random.getrandbits(256))
        print("[+] Salt: %s" % salt)
        commitment = self.ENS.functions.makeCommitment(name, self.ETH_ACCOUNT.address, salt).call()
        print("[+] commitment : %s " % self.w3.toHex(commitment))
        return [salt, commitment]

    def send_commitment(self, commitment):
        print("[+] Sending commit transaction to the network")
        print("[+] commitment: %s" % commitment)
        verify = input("Send transaction? ")
        nonce = self.w3.eth.getTransactionCount(self.ETH_ACCOUNT.address)
        if verify == "y":
            tx_info = self.ENS.functions.commit(commitment).buildTransaction() #transact()
            tx_info['nonce'] = nonce
            signed_tx = self.w3.eth.account.sign_transaction(tx_info, self.p_key)
            commit_tx = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            print("[+] tx hash %s " % self.w3.toHex(commit_tx))
            print("[+] waiting on transaction to be mined")
            self.w3.eth.wait_for_transaction_receipt(commit_tx)
            print("[+] transaction has been mined")
        else:
            exit("[-] transaction cancelled")

    def buy_name(self, salt):
        print("[+] Fetching ENS purchase price")
        price = self.ENS.functions.rentPrice(self.target, self.duration).call()
        print("[+] Price: %f" % price)
        print("[+] Sending Register transaction to the network.")
        verify = input("Send transaction? ")
        if verify == "y":
            tx_info = self.ENS.functions.register(
                self.target,
                self.ETH_ACCOUNT.address,
                self.duration,
                salt
            ).buildTransaction({'value': self.w3.toWei(price, "wei")})
            nonce = self.w3.eth.getTransactionCount(self.ETH_ACCOUNT.address)
            tx_info['nonce'] = nonce
            signed_tx = self.w3.eth.account.sign_transaction(tx_info, self.p_key)
            register_transaction = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            print("[+] tx hash %s " % self.w3.toHex(register_transaction))
            self.w3.eth.wait_for_transaction_receipt(register_transaction)
            print("[+] transaction was mined")
        else:
            exit("[-] transaction cancelled")

    def resolver_multicall(self, calldata_list):

        tx_info = self.ENS_RESOLVER.functions.multicall(calldata_list).buildTransaction()
        nonce = self.w3.eth.getTransactionCount(self.ETH_ACCOUNT.address)
        tx_info['nonce'] = nonce

        signed_tx = self.w3.eth.account.sign_transaction(tx_info, self.p_key)
        register_transaction = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print("[+] tx hash %s " % self.w3.toHex(register_transaction))
        self.w3.eth.wait_for_transaction_receipt(register_transaction)
        print("[+] transaction mined successfully.")
        return

    def read_words(self, word_file):
        file = open(word_file, 'r')
        words_list = file.read().splitlines()
        return words_list

    def read_names_urls(self, file_name):
        with open(file_name, 'r') as data:
            x = []
            y = []
            for line in data:
                p = line.split()
                x.append(p[0])
                y.append(p[1])
        return [x, y]

    def get_register_calldata(self, name, to_address, duration, salt):
        try:
            call_data = self.ENS.encodeABI(fn_name="register", args=[name, to_address, duration, salt]) #[] for none
            return call_data

        except Exception as exception:
            print(exception)
            exit("[-] Could not generate callData")
        return

    def get_commit_calldata(self, commitment):
        try:
            call_data = self.ENS.encodeABI(fn_name="commit", args=[commitment]) #[] for none
            return call_data

        except Exception as exception:
            print(exception)
            exit("[-] Could not generate callData")
        return

    def get_settext_calldata(self, name, key, value):
        full_name = name + '.eth'
        node = ns.namehash(full_name).hex()
        try:
            call_data = self.ENS_RESOLVER.encodeABI(fn_name="setText", args=[node, key, value]) #[] for none
            return call_data

        except Exception as exception:
            print(exception)
            exit("[-] Could not generate callData")
        return

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
            "signer": self.ETH_ACCOUNT,
             "transaction": {
                'chainId': self.chainID,
                'nonce': 0,
                "maxFeePerGas": 0,
                "maxPriorityFeePerGas": 0,
                'gas': 47000,  # added manually, notes above. maybe change back to 300000
                'to': self.w3.toChecksumAddress(self.ENS_REGISTRAR_CONTROLLER), # change to ENS address
                "data": "",
                #"value": self.w3.toWei(self.mint_price * self.how_many, "ether")
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

    def build_bundle(self, bundle_info, method):
        bundle_txs = []  # change to bundle_txs
        tx_cnt = 0
        nonce = self.w3.eth.getTransactionCount(self.ETH_ACCOUNT.address)

        # can't commit & register in one tx because commit has to be 60 seconds old /at least/
        if method == "commit":
            names = bundle_info[0]
            commitments = bundle_info[2]

            # 30 tx's per bundle = 29 + 1 for miner.
            if len(names) > 29:
                print(". Bundle can only hold 29 name transactions and found > 29 Names")
                return

            for idx, name in enumerate(names):

                base_fee = self.w3.eth.fee_history(1, 'latest')
                commit_tx = self.blank_tx()

                commit_tx["transaction"]["nonce"] = nonce + tx_cnt
                commit_tx["transaction"]["gas"] = 46267
                commit_tx["transaction"]["maxFeePerGas"] = math.floor(base_fee["baseFeePerGas"][1] * self.basefee_premium)
                commit_tx["transaction"]["data"] = self.get_commit_calldata(commitments[idx])
                bundle_txs.append(commit_tx)
                tx_cnt += 1

        if method == "register":
            names = bundle_info[0]
            salts = bundle_info[1]
            # gas could be more depending on length of name
            for idx, name in enumerate(names):
                base_fee = self.w3.eth.fee_history(1, 'latest')
                register_tx = self.blank_tx()
                value = self.ENS.functions.rentPrice(name, self.duration).call()
                register_tx["transaction"]["nonce"] = nonce + tx_cnt
                register_tx["transaction"]["gas"] = 210000  # gas requirement changes betwene calls depending on args.
                register_tx["transaction"]["maxFeePerGas"] = math.floor(base_fee["baseFeePerGas"][1] * self.basefee_premium)
                register_tx["transaction"]["data"] = self.get_register_calldata(name, self.ETH_ACCOUNT.address, self.duration, salts[idx])
                register_tx["transaction"]["value"] = value # in wei already
                bundle_txs.append(register_tx)
                tx_cnt += 1

        miner_tx = self.blank_miner_tx()
        base_fee = self.w3.eth.fee_history(1, 'latest')

        miner_tx["transaction"]["maxFeePerGas"] = math.floor(base_fee["baseFeePerGas"][1] * self.basefee_premium)
        miner_tx["transaction"]["nonce"] = nonce + tx_cnt
        value = self.base_tip * len(bundle_info[0])  # self.base_tip 1.5 Gwei * Names = 1.5Gwei per name as tip.
        miner_tx["transaction"]["data"] = self.get_miner_calldata(value)
        miner_tx["transaction"]["value"] = self.w3.toWei(value, "gwei")

        bundle_txs.append(miner_tx)
        return bundle_txs

    def get_commitment_list(self, name_list):
        salts = []
        commitments = []

        for name in name_list:
            commit = self.make_commitment(name)
            salts.append(commit[0])
            commitments.append(commit[1])

        info = [name_list, salts, commitments]
        return info

    def simulate_tx(self, bundle):
        result = self.flashbots.simulate(bundle, block_tag=self.w3.eth.block_number)
        if "error" in result["results"][0]:
            print(result["results"][0])
            exit(f"[-] {result['results'][0]['error']} - check tx and try again.")
        return

    def send_and_wait_flashbots(self, bundle):
        self.simulate_tx(bundle)
        # don't spam the relay.
        block_number = self.w3.eth.blockNumber
        if self.last_sent_block == block_number:
            return False

        result = self.flashbots.send_bundle(bundle, target_block_number=block_number + 1)
        #print(result)
        self.last_sent_block = block_number
        print(f"[+] Bundle broad casted at block {block_number}\n")
        #idk change this to an if/else and return true/false
        try:
            result.wait()
            # receipts = result.receipts()
            # print(receipts)
            print(f"[+] Transaction confirmed at block {self.w3.eth.block_number} [flashbots]")
            return True
        except Exception as exception:
            return False

    def main(self):

        if self.commitment:
            if not self.target:
                exit("[-] No target ENS name provided - needed to generate commitment or purchase.")
            self.make_commitment(self.target)

        if self.commit:
            self.send_commitment(self.commit)

        if self.buy_name_salt:
            if not self.target:
                exit("[-] No target ENS name provided - needed to generate commitment or purchase.")
            self.buy_name(self.buy_name_salt)

        if self.autopilot:
            if not self.target:
                exit("[-] No target ENS name provided - needed to generate commitment or purchase.")
            commitment = self.make_commitment(self.target)
            self.send_commitment(commitment[1])
            time.sleep(62)
            self.buy_name(commitment[0])
            return

        if self.set_avatar_list:
            # batch_avatar -> set multiple names avatars.
            name_info = self.read_names_urls(self.set_avatar_list)  # file of names. [names[], urls[]]
            print("[+] Name -> Avatar URL")

            calldata_list = []

            for idx, name in enumerate(name_info[0]):
                if len(name) < 3:
                    print("[-] found name %s less than 3 characters, remove it and try again." % word)
                    return
                print(f". {name} -> {name_info[1][idx]}") # maybe display prices of desired names and a total cost?

                cd = self.get_settext_calldata(name, "avatar", name_info[1][idx])  # name needs to be keccak
                calldata_list.append(cd)

            self.resolver_multicall(calldata_list)
            return

        if self.list_buy:
            # batch_avatar -> set multiple names avatars.
            list_names = self.read_words(self.list_buy)  # file of names.
            confirmed = False

            print("[+] Names to be registered:")
            for name in list_names:
                if len(name) < 3:
                    print("[-] found name %s less than 3 characters, remove it and try again." % word)
                    return
                print(f". {name}") # maybe display prices of desired names and a total cost?

            commit_info = self.get_commitment_list(list_names)

            while not confirmed:
                commit_bundle = self.build_bundle(commit_info, "commit") # rebuild bundle to update baseFee per run.
                confirmed = self.send_and_wait_flashbots(commit_bundle)

            # reset confirmed loop
            confirmed = False
            print("[+] sleeping for 60 seconds .. minimal commitment time.")
            time.sleep(60)

            while not confirmed:
                register_bundle = self.build_bundle(commit_info, "register")
                confirmed = self.send_and_wait_flashbots(register_bundle)
        return


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="ENSBuyer - lcfr.eth (1/2022)\n")

    parser.add_argument("--name", dest="target_name", type=str,
                        help="Target ENS name to purchase.",
                        default=None)

    parser.add_argument("--makecommitment", dest="make_commitment", action='store_true',
                        help="Generate a salt & commitment for a desired ENS name.",
                        default=False)

    parser.add_argument("--commit", dest="send_commitment", type=str,
                        help="Broadcast generated commitment string to the network for desired ENS name.",
                        default=None)

    parser.add_argument("--buy_wsalt", dest="buy_name", type=str,
                        help="Broadcast purchase transaction to the network for desired ENS name, requires "
                             "pre-commitment. Argument is the salt value used for commitment.",
                        default=None)

    parser.add_argument("--duration", dest="duration", type=int,
                        help="How long to register a name for, default = 1 Year",
                        default=1)

    parser.add_argument("--autopilot", dest="autopilot", action='store_true',
                        help="Autopilot purchases a desired ENS name and performs all the steps automatically",
                        default=False)

    parser.add_argument("--multi_buy", dest="list_names", type=str,
                        help="Filename of names to register, separated line by line.",
                        default=None)

    parser.add_argument("--multi_avatar", dest="set_avatar_list", type=str,
                        help="update multiple ENS avatars with multicall().",
                        default=None)

    parser.add_argument("--basetip", dest="base_tip", type=float,
                        help="Base tip in GWEI - default is 1.5gwei, you can try to set this lower to save on total cost",
                        default=1.5)

    parser.add_argument("--testnet", dest="test_net", action='store_true',
                        help="Enable Testnet",
                        default=False)

    args = parser.parse_args()
    x = ENSBuy(args)
    x.main()
