// SPDX-License-Identifier: MIT
// original hodl.pcc.eth // hodl.esf.eth
// modified lcfr.eth

pragma solidity >=0.7.0 <0.9.0;

import "https://github.com/Arachnid/solidity-stringutils/blob/master/src/strings.sol";
import "@ensdomains/ens-contracts/contracts/registry/ENS.sol";

struct Account {
    string name;
    address addr;
    bool resolved;
}

interface IRegistrar  {
     function node(address _addr) external view returns (bytes32);
}

interface IResolver {
    function name(bytes32 _node) external view returns (string memory);
    function addr(bytes32 _node) external view returns (address);
}

contract AddressLookup {
    using strings for *;

    address constant REVERSE_REGISTRAR_ADDRESS = 0x084b1c3C81545d370f3634392De611CaaBFf8148;
    address constant REVERSE_RESOLVER_ADDRESS = 0xA2C122BE93b0074270ebeE7f6b7292C7deB45047;
    address constant ENS_ADDRESS = 0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e;

    IResolver  reverse_resolver  = IResolver(REVERSE_RESOLVER_ADDRESS);
    IRegistrar reverse_registrar = IRegistrar(REVERSE_REGISTRAR_ADDRESS);

    ENS public ens = ENS(ENS_ADDRESS);

    function getAccountNames(address[] memory _addr) public view returns(Account[] memory) {

        Account[] memory names = new Account[](_addr.length);

        for(uint256 i; i < _addr.length;){

            address currentAddress = _addr[i];
            bytes32 reverse_node = reverse_registrar.node(currentAddress);
            string memory name = reverse_resolver.name(reverse_node);

            bytes32 node = getDomainHash(name);
            (bool success, bytes memory data) = address(ens.resolver(node)).staticcall(abi.encodeWithSignature("addr(bytes32)", node));
            if(success){
                address addr = bytesToAddress(data);
                if (addr == currentAddress){
                    // resolver && reverse == foward
                    names[i] = Account(name, currentAddress, true);
                } else {
                    // resolver && reverse != foward
                    names[i] = Account(name, currentAddress, false);
                }
            } else {
                // no resolver
                names[i] = Account(name, currentAddress, false);
            }
            unchecked { ++i; }
        }
        return names;
    }

    function bytesToAddress(bytes memory bys) private pure returns(address addr) {
        assembly {
            addr := mload(add(bys,32))
        } 
    }

    function getParts(string memory _string) public view returns(string[] memory) {
        strings.slice memory delim = ".".toSlice();
        strings.slice memory _string = _string.toSlice();
        uint256 count = _string.count(delim);

        if (count == 0){
            string[] memory x = new string[](0);
            return x;
        }

        string[] memory parts = new string[](_string.count(delim) + 1);
        for(uint i = 0; i < parts.length; i++) {
            parts[i] = _string.split(delim).toString();
        }
        return parts;
    }

    ///this is the correct method for creating a 2 level ENS namehash
    function getDomainHash(string memory _ensName) public view returns (bytes32 namehash) {
        string[] memory _arr = getParts(_ensName);
        namehash = 0x0;

        for(uint256 i; i < _arr.length;){
            unchecked{ ++i; }
            namehash = keccak256(abi.encodePacked(namehash, keccak256(abi.encodePacked(_arr[_arr.length - i]))));               
        }
        return namehash;
    }
    
}
