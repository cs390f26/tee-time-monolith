# Deploy on EC2

This document explains how to run the monolithic voting app on an EC2 instance.


## One-Time Setup

The file file `deploy/userdata.sh` is used in the deployment process, and you must change one line before you deploy

* Open `deploy/userdata.sh` in Cursor or `nano`.
* Near the top of the file you will find the line:

  ```
  REPO_URL="https://github.com/YOUR_GITHUB_USERNAME/tee-time-monolith.git"
  ```
* Change `YOUR_GITHUB_USERNAME` to your Github username.
* Commit this change to the git repo, and push it back to your Github account

  ```
  git add deploy/userdata.sh
  git commit -m "set github account"
  git push origin main
  ```


If the `git push` command fails, check the url of `origin` and make sure it points at your fork of the repo

  ```
  git remote -v
  ```


## Deploy Process

The steps necessary to deploy are:

* Install necessary packages
* Clone the repo
* Setup the `.venv`
* Use the example `.env` file for configuration
* Download DynamoDB Local
* Setup systemd services for DynamoDB Local and Gunicorn
* Launch DynamoDB
* Create the table
* Launch Gunicorn


The script `deploy/userdata.sh` contains all these steps, and we can tell EC2 to run these commands at launch by putting the contents of this script in the [Cloud-init](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html#userdata-linux) which is under the userdata section of the EC2 launch wizard.

In the Launch dialog:

* (Optional, but encouraged) Name the instance "Voting app"
* Use the default `t3.micro` instance type
* Select your `vockey` for authentication
* Ensure that HTTP and SSH are enabled in the security group
* Open the "Advanced" tab, and scroll to the bottom.
* Paste the contents of `deploy/userdata.sh` into **User data**


When you launch the instance, AWS will boot the instance, and then run the userdata script.  This will take a minute or two, but once it completes DynamoDB Local and Gunicorn will be running (i.e. the app will be deployed).


## Debugging

The Cloud-init process writes out output of the userdata script to `/var/log/cloud-init-output.log`.  If the app does not start, SSH to the instance and look at this file to understand what failed.


## Other Useful Commands on the EC2 Instance

- `systemctl status voting` — see the status of the Gunicorn process
- `systemctl status dynamodb-local` — see the status of the DynamoDB Local process
- `curl -s http://localhost/health` — make a call to the `/health` endpoint, which returns a 200-status code if the web server is running and it can communicate with DynamoDB Local
- `sudo systemctl restart voting` — restart the web process after a config or code change
- `sudo journalctl -u voting -f` — follow the voting (gunicorn) logs
- `sudo journalctl -u dynamodb-local -f` — follow the DynamoDB Local logs
