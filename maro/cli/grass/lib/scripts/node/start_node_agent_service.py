# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.


import argparse
import json
import os
import sys
from pathlib import Path

from ..utils.details import load_cluster_details
from ..utils.subprocess import SubProcess

START_SERVICE_COMMAND = """\
systemctl --user daemon-reload
systemctl --user start maro-node-agent.service
systemctl --user enable maro-node-agent.service
loginctl enable-linger {admin_username}  # Make sure the user is not logged out
"""

if __name__ == "__main__":
    # Load args
    parser = argparse.ArgumentParser()
    parser.add_argument("cluster_name")
    parser.add_argument("node_name")
    args = parser.parse_args()

    # Load details
    cluster_details = load_cluster_details(cluster_name=args.cluster_name)
    admin_username = cluster_details["user"]["admin_username"]
    master_hostname = cluster_details["master"]["hostname"]
    redis_port = cluster_details["master"]["redis"]["port"]

    # Dump node_agent.config
    os.makedirs(os.path.expanduser("~/.maro-local/agents/"), exist_ok=True)
    with open(os.path.expanduser("~/.maro-local/agents/maro-node-agent.config"), "w") as fw:
        json.dump({
            "cluster_name": args.cluster_name,
            "node_name": args.node_name,
            "master_hostname": master_hostname,
            "redis_port": redis_port
        }, fw)

    # Load .service
    with open(os.path.expanduser("~/.maro/lib/grass/agents/systemd/maro-node-agent.service"), "r") as fr:
        service_file = fr.read()

    # Rewrite data in .service and write it to systemd folder
    service_file = service_file.format(home_path=str(Path.home()))
    os.makedirs(os.path.expanduser("~/.config/systemd/user/"), exist_ok=True)
    with open(os.path.expanduser("~/.config/systemd/user/maro-node-agent.service"), "w") as fw:
        fw.write(service_file)

    # Exec command
    command = START_SERVICE_COMMAND.format(admin_username=admin_username)
    return_str = SubProcess.run(command=command)
    sys.stdout.write(return_str)
