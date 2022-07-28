from duneanalytics import DuneAnalytics
from ast import literal_eval
from web3 import Web3, HTTPProvider

import datetime, json, tweepy, time, os


class ENSReleased:
    def __init__(self):
        self.provider = os.getenv("PROVIDER_URL")
        self.oauth_key = os.getenv("OAUTH_KEY")
        self.oauth_secret = os.getenv("OAUTH_SECRET")
        self.access_token = os.getenv("ACCESS_TOKEN")
        self.access_token_secret = os.getenv("ACCESS_SECRET")
        self.dune_user = os.getenv("DUNE_USER")
        self.dune_pass = os.getenv("DUNE_PASS")

        self.w3 = Web3(HTTPProvider(self.provider))
        self.ENS_BASE_REGISTRAR = "0x57f1887a8bf19b14fc0df6fd9b2acc9af147ea85"
        self.br_abi_json = json.loads(open('./abi/' + self.ENS_BASE_REGISTRAR + '.json', 'r').read())
        self.ENS_REGISTRAR = self.w3.eth.contract(address=self.w3.toChecksumAddress(self.ENS_BASE_REGISTRAR), abi=self.br_abi_json)
        self.grace_period = 7776000

        self.auth = tweepy.OAuthHandler(self.oauth_key, self.oauth_secret)
        self.auth.set_access_token(self.access_token, self.access_token_secret)

        self.api = tweepy.API(self.auth)

        self.dune = DuneAnalytics(self.dune_user, self.dune_pass)
        self.dune.login()
        self.dune.fetch_auth_token()
        return

    def derive_token_from_name(self, name):
        token_id = literal_eval(Web3.keccak(text=name).hex())
        return token_id

    def get_expiration(self, token_id):
        expiration_date = self.ENS_REGISTRAR.functions.nameExpires(token_id).call()
        return expiration_date

    def login_twitter(self):
        try:
            self.api.verify_credentials()
            print("[+] Authentication OK")
        except:
            exit("[-] Error during authentication")

    def get_names_from_dune(self):
        result_id = self.dune.query_result_id(query_id=349395)
        data = self.dune.query_result(result_id)
        expiring = []
        # parse the name from the Dune results
        # Get the expiration for name from contract and add the grace_period
        # save it in a master list as [[name : total_expiration]]
        # using %m-%d-%Y %H:%M:%S format displays to the second vs the minute displayed on the website.
        for table in data["data"]["get_result_by_result_id"]:
            # add name + total_expiration(including grace_period to list)
            name = table["data"]["name"]
            time = datetime.datetime.fromtimestamp(
                self.get_expiration(self.derive_token_from_name(name)) + self.grace_period
            ).strftime("%m-%d-%Y %H:%M:%S")
            info = [name, time]
            expiring.append(info)
        return expiring

    def isascii(self, s):
        return len(s) == len(s.encode())

    def hascaps(self, s):
        for letter in s:
            if letter.isupper():
                return True
        return False

    def name_to_twitter(self, expiring):
        final_period = []
        post_string = ""

        for name in expiring:
            ensname = name[0]
            date = name[1]
            to_string = f"[+] {ensname}.eth <-> {date}"

            if not self.isascii(ensname):
                to_string = f"[+] {ensname}.eth (invalid:non-ascii) <-> {date}"

            if self.hascaps(ensname):
                to_string = f"[+] {ensname}.eth (invalid:caps) <-> {date}"

            final_period.append(to_string)

        print(final_period)
        for idx, expiration in enumerate(final_period):
            post_string += expiration + "\n"
            if idx % 3 == 0:
                message = "$ENS names releasing in 24HRs:"
                self.api.update_status(message+"\n\n"+post_string+"\n\n")
                print(post_string)
                post_string = ""
                time.sleep(60)
        return
    def main(self):
        self.login_twitter()
        expiring = self.get_names_from_dune()
        self.name_to_twitter(expiring)
        return


if __name__ == '__main__':
    print("[+] ENS Released Twitter Bot - lcfr.eth 01/2022")
    ENSReleased().main()
