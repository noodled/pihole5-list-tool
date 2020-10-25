#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2020 jessedp
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"),  to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


"""Makes bulk adding DNS blocklists and allowlists to Pi-hole 5 a breeze"""

import os
import sys
import sqlite3
import requests

from colors import color


import constants
import prompts
import blocklists
import utils

__version__ = "0.5.1"


ANUDEEP_ALLOWLIST = (
    "https://raw.githubusercontent.com/anudeepND/whitelist/master/domains/whitelist.txt"
)
whiteLists = {
    constants.W_ANUDEEP_ALLOW: {
        "url": ANUDEEP_ALLOWLIST,
        "comment": "AndeepND | Allowlist Only",
    },
    constants.W_ANUDEEP_REFERRAL: {
        "url": "https://raw.githubusercontent.com/anudeepND/whitelist/master/domains/referral-sites.txt",
        "comment": "AndeepND | Allowlist+Referral",
    },
    constants.W_ANUDEEP_OPTIONAL: {
        "url": "https://raw.githubusercontent.com/anudeepND/whitelist/master/domains/optional-list.txt",
        "comment": "AndeepND | Allowlist+Optional",
    },
}


def main():
    """main method"""
    conn = None
    try:
        utils.clear()
        print(color("    ┌──────────────────────────────────────────┐", fg="#b61042"))
        print(
            color("    │       ", fg="#b61042")
            + color(f"π-hole 5 list tool  v{__version__}", "#FFF")
            + color("         │", fg="#b61042")
        )
        print(color("    └──────────────────────────────────────────┘", fg="#b61042"))
        utils.info("    https://github.com/jessedp/pihole5-list-tool\n")

        db_file = ""
        use_docker = False
        docker = utils.find_docker()

        if docker[0] is True:
            utils.success(f"Found Running Docker config: {docker[1]}")
            use_docker = prompts.confirm("Use Docker-ized config?", "n")
            if use_docker:
                db_file = docker[1]

        if not use_docker:
            db_file = prompts.ask_db()

        # ask_db validates the db, pass this connectoin around for easy access & "global" mgmt
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()

        list_type = prompts.ask_list_type()

        print()
        utils.danger("    Do not hit ENTER or Y if a step seems to hang!")
        utils.danger("    Use CTRL+C if you're sure it's hung and report it.\n")

        if list_type == constants.BLOCKLIST:
            save = blocklists.manage_blocklists(cur)

        if list_type == constants.ALLOWLIST:
            save = process_allowlists(db_file)

        if not save:
            conn.close()
            utils.warn("\nNothing changed. Bye!")
            sys.exit(0)

        conn.commit()
        conn.close()

        if prompts.confirm("Update Gravity for immediate effect?"):
            print()
            if use_docker:
                os.system('docker exec pihole bash "/usr/local/bin/pihole" "-g"')
            else:
                os.system("pihole -g")
        else:
            if use_docker:
                utils.info(
                    "Update Gravity through the web interface or by running:\n\t"
                    + '# docker exec pihole bash "/usr/local/bin/pihole" "-g"'
                )

            else:
                utils.info(
                    "Update Gravity through the web interface or by running:\n\t# pihole -g"
                )

            utils.info("\n\tBye!")

    except (KeyboardInterrupt, KeyError):
        if conn:
            conn.close()
        sys.exit(0)


def process_allowlists(db_file):
    """ prompt for and process allowlists """
    source = prompts.ask_allowlist()

    import_list = []

    if source in whiteLists:
        url_source = whiteLists[source]
        resp = requests.get(url_source["url"])
        import_list = utils.process_lines(resp.text, url_source["comment"], False)
        # This breaks if we add a new whitelist setup
        if source != ANUDEEP_ALLOWLIST:
            resp = requests.get(ANUDEEP_ALLOWLIST)
            import_list += utils.process_lines(resp.text, url_source["comment"], False)

    if source == constants.FILE:
        fname = prompts.ask_import_file()
        import_file = open(fname)
        import_list = utils.process_lines(import_file.read(), f"File: {fname}", False)

    if source == constants.PASTE:
        import_list = prompts.ask_paste()
        import_list = utils.process_lines(
            import_list, "Pasted content", utils.validate_host
        )

    if len(import_list) == 0:
        utils.die("No valid urls found, try again")

    if not prompts.confirm(f"Add {len(import_list)} white lists to {db_file}?"):
        utils.warn("Nothing changed. Bye!")
        sys.exit(0)

    conn = sqlite3.connect(db_file)
    sqldb = conn.cursor()
    added = 0
    exists = 0

    for item in import_list:
        sqldb.execute(
            "SELECT COUNT(*) FROM domainlist WHERE domain = ?", (item["url"],)
        )

        cnt = sqldb.fetchone()

        if cnt[0] > 0:
            exists += 1
        else:
            # 0 = exact whitelist
            # 2 = regex whitelist
            domain_type = 0
            if item["type"] == constants.REGEX:
                domain_type = 2

            vals = (item["url"], domain_type, item["comment"])
            sqldb.execute(
                "INSERT OR IGNORE INTO domainlist (domain, type, comment) VALUES (?,?,?)",
                vals,
            )
            conn.commit()
            added += 1

    sqldb.close()
    conn.close()

    utils.success(f"{added} whitelists added! {exists} already existed.")


if __name__ == "__main__":
    try:
        main()
    except sqlite3.OperationalError as err:
        utils.danger("\n\tDatabase error!")
        utils.danger(f"\t{err}")
    except (KeyboardInterrupt, KeyError):
        sys.exit(0)
