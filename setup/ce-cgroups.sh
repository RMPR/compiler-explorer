# Note: this is only the setup for cgroups v2 since this is what modern versions of Ubuntu use.
sudo apt-get install cgroup-tools
sudo cgcreate -a $USER:$USER -g memory,pids,cpu:ce-sandbox
sudo cgcreate -a $USER:$USER -g memory,pids,cpu:ce-compile
sudo chown $USER:root /sys/fs/cgroup/cgroup.procs

sudo sysctl -w kernel.apparmor_restrict_unprivileged_unconfined=0
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0