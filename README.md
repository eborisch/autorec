# autorec
Automated reconstruction job submission tool.

Installation:
 *  Copy this directory and its contents to the acquiring MRI system. We'll
    refer to the location as AR_PATH.
 *  Create AR_PATH/ar_lib/site-local.py (can be site-ANY.py). Set (at a minimum)
    DEFAULT_RECON_MACHINES (tuple of ip addresses.) See AR_PATH/ar_lib/arsite.py
    for other variables that can be set.
 *  Create a pre-shared (passwordless) SSH key:
    ```
    cd AR_PATH
    ssh-keygen -f id_recon
    ```
    Hit return without entering a password (twice).
 *  Copy the created id_recon.pub into your reconstruction user's
    `~/.ssh/authorized_keys` (`~/.ssh` and `~/.ssh/authorized_keys` must not be
    world read/writeable) on DEFAULT_RECON_MACHINES[0]. (Assuming it connects, it
    will attempt DEFAULT_RECON_MACHINES[1] ... if provided and [0] fails.)
 *  Execute AR_PATH/ar_lib/ssh.py to test SSH connectivity.
 *  Enter AR_PATH/connectionTest and run `./connectionTest` (Will create files
    in ~USERNAME/incoming/testing on reconstruction system.)

To run automatically after an acquisition:
 *  Create reconNNNN/conf.py (copy template/conf.py)
 *  Edit the new conf.py to reflect your needs (files to fransfter, etc.)
 *  Place a symlink to autorec.py in /usr/g/bin matching the son-of-recon
    (rhrecon) value; for example:
    `ln -s AR_PATH/autorec.py /usr/g/bin/recon1234`
 *  Note the symlink name is used to determine what directory (and associated
    conf.py file) to use.
 *  Logs are created in AR_PATH/reconNNNN/logs/JOB_DESCRIPTOR/

DOIs for individual releases available at: https://doi.org/10.5281/zenodo.2739230
