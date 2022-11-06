# Rescuing ENS names from compromised wallets (overview).

![image](./nick.png)

Inspired by nick.eth's twitter post [here](https://twitter.com/nicksdjohnson/status/1527065045678452736)

Often times when a wallet is compromised the attacker will leave some assets as a trap for the owner.

The trap works as follows: 
1) The attacker leaves some tokens in the compromised wallet but drains all the ether.
2) This means the owner can not transfer the tokens in the wallet until they send it more ether to cover the gas fee.
3) wait for the legitimate owner to try and save their precious tokens by sending eth to cover the gas fees of transferTo and and rob them again.

A "sweeper" loads a private key and attempts to send the full balance in a loop without much worry about processing power.
Enabling it to run indefinately for free or until cancelled/closed.

The problem being how does the hacked user send ether to the compromised account to fund the transaction of saving our tokens?

# Enter Flashbots bundles & sponsored transactions:
[https://github.com/flashbots/searcher-sponsored-tx](https://github.com/flashbots/searcher-sponsored-tx)

Sponsored transactions allow for one address to pay for the fees of another address's transaction by paying the miner directly using 
the solidity global block.coinbase. block.coinbase is a payable alias to the current block miners coinbase/payment address.

[https://docs.soliditylang.org/en/latest/units-and-global-variables.html](https://docs.soliditylang.org/en/latest/units-and-global-variables.html)

A simple contract below demonstrates fowarding payments to a miner:

```commandline
pragma solidity ^0.8.7;
contract MinerPayment {
    function payMiner() external payable {
        block.coinbase.transfer(msg.value);
    }
}
```


The flashbots team has deployed a simple contract which can be used for this here: [CheckAndSend Contract](https://etherscan.io/address/0xc4595e3966e0ce6e3c46854647611940a09448d3#code)

Next we need to understand a few EIP1559 specifics such as MaxFeePerGas, MaxPriorityFeePerGas and the blocks baseFee 
and how they are used to calculate the gas fee/cost of a transaction. This won't be covered.

For an overview of EIP1559 Gas description you can read [here](https://docs.alchemy.com/alchemy/guides/eip-1559/maxpriorityfeepergas-vs-maxfeepergas)

A note on transactions - an address must /always/ have the gas in its own balance to cover the block baseFee amount.

A sponsored transaction can only cover the MaxPriorityFeePerGas for another transaction and not the MaxFeePerGas.
[More info](https://docs.flashbots.net/flashbots-auction/searchers/advanced/eip1559)

How do we send the address ether to cover the gas fee for MaxFeePerGas without the attackers robbing it?

# Flashbots bundles

Flashbots works by sending bundles of transactions in a sort of private pool where people bid/pay miners directly.

A bundle is an array of transactions which will be executed consecutively in the same block/transaction. If any transaction
in the bundle shall fail the whole bundle will revert.

Users do not pay for failed transactions while using flashbots for submitting bundles.

[More info on FlashBots](https://docs.flashbots.net/flashbots-auction/overview)

The real magic that allows us to save tokens is the bundle functionality + sponsored transactions to be able to execute
the bundle from another wallet besides the compromised wallet. Not the fact that the transactions are "private".


# Counter Attack
With the knowledge of bundles in hand we can create a bundle of 3 transactions to accomplish this which will all be executed as if they were a single transaction in a single block.

TX 1 - send eth from another wallet to the compromised wallet to cover block baseFee.

TX 2 - transferTo the token from the compromised wallet to the rescuer wallet.

TX 3 - execute & pay for the transaction using sponsored transaction from the rescuer wallet via block.coinbase

# Install
python3 -m venv env  
source ./env/bin/activate  
pip install web3py  
pip install flashbots  

# usage example

use --auto to return all names owned by a compromised key and rescue all of them. 

```commandline

export NODE=https://mainnet.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4XXX

ENSRescuer.py --auto --hacked-key=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA --rescuer-key=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

[+] rescuing names from: 0xd175B9609d20B6A0A8297945c8339a0D571EECEa.
[+] sending rescued names to: 0x9E5916079eD74C38FaA3322bDAec62307beA1D9b.
[+] Auto Rescuing all names!
[+] Found jjhgjhgjggg777.eth
[+] Performing rescue operation
[+] Bundle broad casted at block 15913187

[+] Bundle broad casted at block 15913188
..
[+] Transaction confirmed at block 15913188 [flashbots]
```

Rescuing a specific name - hero.eth  

```commandline
export NODE=https://mainnet.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4XXX

ENSRescue.py --name hero --hacked-key AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA --rescuer-key xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
[+] testnet enabled, connected to goerli infura node.
[+] rescuing names from: 0x59a02AA24367b293902002f1Df1F5D55e76B5b4C.
[+] sending rescued names to: 0x328eBc7bb2ca4Bf4216863042a960E3C64Ed4c10.
[+] Rescuing hero!
[+] token_id of hero.eth : 111124751542167998813960028570131154730449316884244675085439636823004772343202
[+] Bundle broad casted at block 6914883
...
[+] Bundle broad casted at block 6914888

[AttributeDict({'blockHash': HexBytes('0x342e7a0583e970df5c26bd5510331c681c01367921b182fcd1748674ecbf95e2'), 'blockNumber': 6914889, 'contractAddress': None, 'cumulativeGasUsed': 21000, 'effectiveGasPrice': 8, 'from': '0x328eBc7bb2ca4Bf4216863042a960E3C64Ed4c10', 'gasUsed': 21000, 'logs': [], 'logsBloom': HexBytes('0x00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'), 'status': 1, 'to': '0x59a02AA24367b293902002f1Df1F5D55e76B5b4C', 'transactionHash': HexBytes('0x9845e7f18876f676b787af1a9bad1f2c8d587ef1d05691eeefedae71b4764ec8'), 'transactionIndex': 0, 'type': '0x2'}), AttributeDict({'blockHash': HexBytes('0x342e7a0583e970df5c26bd5510331c681c01367921b182fcd1748674ecbf95e2'), 'blockNumber': 6914889, 'contractAddress': None, 'cumulativeGasUsed': 62215, 'effectiveGasPrice': 8, 'from': '0x59a02AA24367b293902002f1Df1F5D55e76B5b4C', 'gasUsed': 41215, 'logs': [AttributeDict({'address': '0x57f1887a8BF19b14fC0dF6Fd9B2acc9Af147eA85', 'blockHash': HexBytes('0x342e7a0583e970df5c26bd5510331c681c01367921b182fcd1748674ecbf95e2'), 'blockNumber': 6914889, 'data': '0x', 'logIndex': 0, 'removed': False, 'topics': [HexBytes('0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'), HexBytes('0x00000000000000000000000059a02aa24367b293902002f1df1f5d55e76b5b4c'), HexBytes('0x000000000000000000000000328ebc7bb2ca4bf4216863042a960e3c64ed4c10'), HexBytes('0xf5ae61672361c474f5ea3e994da5ef9670fc4455792bd5cc81189dd6b2dc9da2')], 'transactionHash': HexBytes('0xb82841e22c1e6c7e1c443fc9d938b9e42b6318d7b505e47efc581cda4528d853'), 'transactionIndex': 1})], 'logsBloom': HexBytes('0x00000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010100000000000000000000000000000000004000040000000000000000000000000000000000000000000000000004000000004000000000000000000000000000000000000400002000080000000000000000000000000000000000000080000820000000000000000000000000000000000000000000000000000000000000000002000'), 'status': 1, 'to': '0x57f1887a8BF19b14fC0dF6Fd9B2acc9Af147eA85', 'transactionHash': HexBytes('0xb82841e22c1e6c7e1c443fc9d938b9e42b6318d7b505e47efc581cda4528d853'), 'transactionIndex': 1, 'type': '0x2'}), AttributeDict({'blockHash': HexBytes('0x342e7a0583e970df5c26bd5510331c681c01367921b182fcd1748674ecbf95e2'), 'blockNumber': 6914889, 'contractAddress': None, 'cumulativeGasUsed': 93196, 'effectiveGasPrice': 8, 'from': '0x328eBc7bb2ca4Bf4216863042a960E3C64Ed4c10', 'gasUsed': 30981, 'logs': [], 'logsBloom': HexBytes('0x00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'), 'status': 1, 'to': '0xFee1708400f01f2Bb8848Ef397C1a2F4C25c910B', 'transactionHash': HexBytes('0x5191f545478467cde77fad24a937a18e7778775402f5459b3cd0f2e6f6645136'), 'transactionIndex': 2, 'type': '0x2'})]

[+] Transaction confirmed at block 6914889 [flashbots]

